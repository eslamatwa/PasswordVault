"""The Windows half of auto-type: one hotkey in, keystrokes out.

Everything that decides *what* to send lives in `autotype_match` and
`autotype_sequence`, tested without a keyboard. This module is the part
that cannot be tested that way, so it is kept as small and as dull as
possible.

Two choices worth stating, because both are about not being a keylogger:

`RegisterHotKey`, not `SetWindowsHookEx`. Windows tells this process
about the one combination it asked for and nothing else. A low-level
keyboard hook would receive every keystroke on the machine — that is what
a keylogger is, it is what antivirus software will call it, and a
password manager has no business doing it to read one shortcut.

Neither call needs administrator rights, which is the standing rule for
this app. The consequence is that a window running elevated cannot be
typed into: Windows refuses input from a lower integrity level. That is
accepted rather than worked around; asking a password manager to run
elevated to fix it would be a far worse trade.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from ctypes import wintypes

log = logging.getLogger("PasswordVault")

IS_WINDOWS = sys.platform == "win32"

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# A gap between keystrokes. Sending a whole password in one burst loses
# characters in remote sessions and in anything doing its own input
# handling -- an RDP client, a terminal, a web form with a JS mask.
KEY_GAP_SEC = 0.004

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = (ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8
                 else ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        # The union is as large as its biggest member, MOUSEINPUT — 32
        # bytes on 64-bit. Sizing it by hand to KEYBDINPUT instead makes
        # every INPUT 8 bytes short, and SendInput rejects the lot
        # without saying why: it returns 0 and the keystrokes simply do
        # not happen.
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    # Without these, 64-bit handles are truncated to int and pointers are
    # marshalled wrongly. Both fail quietly rather than loudly.
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT),
                                 ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR,
                                      ctypes.c_int)
    user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int,
                                      wintypes.UINT, wintypes.UINT)
    user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND


def available() -> bool:
    return IS_WINDOWS


# ─── Looking at the window in front ──────────────────────────
def foreground() -> tuple[int, str]:
    """The window the user is actually in: ``(handle, title)``."""
    if not IS_WINDOWS:
        return 0, ""
    handle = user32.GetForegroundWindow()
    if not handle:
        return 0, ""
    length = user32.GetWindowTextLengthW(handle)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buffer, length + 1)
    return int(handle), buffer.value


GA_ROOT = 2


def top_level(handle: int) -> int:
    """The real top-level window for *handle*.

    Tk on Windows wraps each toplevel: `winfo_id()` gives the inner
    child HWND, while `GetForegroundWindow` reports the wrapper around
    it. Comparing the two directly never matches, so the check for "is
    this one of our own windows" silently never fired — and auto-type
    would have typed the password into the vault's own search box.
    """
    if not IS_WINDOWS or not handle:
        return handle
    root = user32.GetAncestor(wintypes.HWND(handle), GA_ROOT)
    return int(root) if root else handle


def refocus(handle: int) -> bool:
    """Put *handle* back in front, after the picker took focus away."""
    if not IS_WINDOWS or not handle:
        return False
    if not user32.IsWindow(handle):
        return False
    user32.SetForegroundWindow(handle)
    # SetForegroundWindow is advisory: the shell refuses it when another
    # process owns the foreground. Confirm rather than assume, because
    # what follows is typing a password.
    for _ in range(20):
        if user32.GetForegroundWindow() == handle:
            return True
        time.sleep(0.01)
    return False


# ─── Sending keystrokes ──────────────────────────────────────
def _key_event(vk: int, scan: int, flags: int) -> "INPUT":
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.union.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return event


def _send(events) -> bool:
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        log.warning("SendInput sent %d of %d events (error %d).",
                    sent, len(events), ctypes.get_last_error())
        return False
    return True


def type_text(text: str) -> bool:
    """Type *text* as characters, whatever the keyboard layout is.

    KEYEVENTF_UNICODE sends the character itself rather than the key that
    would produce it, so a password with symbols arrives intact on an
    Arabic layout, a French one, or anything else. Values are sent as
    UTF-16 code units, which is what this API takes -- a character
    outside the basic plane is two of them.
    """
    if not IS_WINDOWS or not text:
        return True
    encoded = text.encode("utf-16-le")
    units = [int.from_bytes(encoded[i:i + 2], "little")
             for i in range(0, len(encoded), 2)]
    for unit in units:
        ok = _send([_key_event(0, unit, KEYEVENTF_UNICODE),
                    _key_event(0, unit,
                               KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        if not ok:
            return False
        time.sleep(KEY_GAP_SEC)
    return True


_VK = {"tab": 0x09, "enter": 0x0D, "space": 0x20, "escape": 0x1B,
       "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23}


def press(name: str) -> bool:
    """Press a named key, such as Tab or Enter."""
    if not IS_WINDOWS:
        return True
    vk = _VK.get(name)
    if vk is None:
        log.warning("Auto-type asked for an unknown key %r.", name)
        return False
    ok = _send([_key_event(vk, 0, 0), _key_event(vk, 0, KEYEVENTF_KEYUP)])
    time.sleep(KEY_GAP_SEC)
    return ok


def perform(steps, values, still_ok=None) -> bool:
    """Carry out parsed steps, checking before each that it is still safe.

    *still_ok* is called before every step and must return True for it to
    happen. It is how the window being switched away mid-sequence stops
    the rest -- the password half of a login is the half that must never
    land somewhere else.
    """
    for kind, value in steps:
        if still_ok is not None and not still_ok():
            log.warning("Auto-type stopped: the target window changed.")
            return False
        if kind == "text":
            ok = type_text(value)
        elif kind == "field":
            ok = type_text(values.get(value, ""))
        elif kind == "key":
            ok = press(value)
        elif kind == "delay":
            time.sleep(min(value, 10000) / 1000)
            ok = True
        else:
            log.warning("Auto-type met an unknown step %r.", kind)
            ok = False
        if not ok:
            return False
    return True


# ─── The hotkey listener ─────────────────────────────────────
class HotkeyListener:
    """Registers hotkeys on a thread of its own and reports presses.

    `RegisterHotKey` delivers WM_HOTKEY to the thread that registered it,
    so that thread needs a message loop. Tk has its own loop and will not
    share it, hence a second thread whose only job is to wait.

    Presses are handed back through `deliver`, which the app points at
    `root.after` — Tk may only be touched from the thread running its
    main loop.
    """

    def __init__(self, deliver):
        self._deliver = deliver
        self._thread = None
        self._thread_id = None
        self._wanted: dict[int, tuple[int, int]] = {}
        self._names: dict[int, str] = {}
        self.failures: dict[str, str] = {}
        self._ready = threading.Event()

    def start(self, shortcuts: dict) -> None:
        """*shortcuts* maps a name to a ``(modifiers, key)`` pair."""
        self.stop()
        self.failures = {}
        self._wanted = {}
        self._names = {}
        for index, (name, combo) in enumerate(shortcuts.items(), start=1):
            self._wanted[index] = combo
            self._names[index] = name
        if not self._wanted or not IS_WINDOWS:
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="autotype-hotkeys")
        self._thread.start()
        # Registration happens on that thread; wait so the caller can
        # report a clash straight away rather than a second later.
        self._ready.wait(timeout=2.0)

    def stop(self) -> None:
        if self._thread and self._thread.is_alive() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        registered = []
        try:
            for ident, (modifiers, key) in self._wanted.items():
                if user32.RegisterHotKey(None, ident, modifiers, key):
                    registered.append(ident)
                else:
                    name = self._names.get(ident, str(ident))
                    self.failures[name] = (
                        "another program is already using it")
                    log.warning("Could not register the %s hotkey; "
                                "another program holds it.", name)
        finally:
            self._ready.set()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                name = self._names.get(int(message.wParam))
                if name:
                    try:
                        self._deliver(name)
                    except Exception:  # noqa: BLE001 - a callback must
                        # never take the listener thread down with it.
                        log.exception("Auto-type hotkey handler failed.")

        for ident in registered:
            user32.UnregisterHotKey(None, ident)
