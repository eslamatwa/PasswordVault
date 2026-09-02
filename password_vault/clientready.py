"""Is the SSH client actually up yet?

Some clients are one process with many tabs. MobaXterm is the one that
matters here: `MobaXterm.exe -newtab "..."` does not start a session
itself, it hands the command to an already-running MobaXterm and exits.
`subprocess.Popen` returns successfully either way, so the launch looks
like it worked whether a tab opened or nothing happened at all.

That is the failure this module exists for. When MobaXterm is not running
yet, the first launch starts it -- and starting it takes seconds, not
milliseconds. Every handoff that arrives before it is ready has nothing
to be handed to. Ask for four sessions from a cold start and one or two
open, which is exactly what it looks like from the outside: no error, no
log line, just fewer terminals than you asked for.

Spacing the launches further apart is not a fix, it is a longer guess. So
the batch waits for the window instead: a top-level window belonging to a
process running that executable is the client saying it is ready to be
talked to. If it never appears, the batch goes ahead anyway and says so
-- a slow machine should mean a slow start, not a refusal.

PuTTY and Windows SSH each get their own process and window per session,
so none of this applies to them and none of it runs.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

log = logging.getLogger("PasswordVault")

IS_WINDOWS = sys.platform == "win32"

# Clients where one process serves every session, so a second launch is a
# handoff rather than a start. Everything not named here gets its own
# process and needs no waiting.
SINGLE_INSTANCE = frozenset({"MobaXterm"})

# How long a cold start is given before the batch continues regardless.
# MobaXterm loading its plugins off a slow disk is unhurried; a ceiling
# this high costs nothing when the client is already running, because
# then the very first check passes.
READY_TIMEOUT_MS = 30_000

# How often to look. Frequent enough not to add a visible delay of its
# own once the window is up.
READY_POLL_MS = 250

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                   wintypes.LPARAM)

    user32.EnumWindows.argtypes = (ENUM_PROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    # Without these the handle comes back truncated to 32 bits and every
    # lookup fails -- the same trap the auto-type window code hit.
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD,
                                                  wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.restype = wintypes.BOOL


def is_single_instance(client_name: str) -> bool:
    """Whether a second launch of this client is a handoff, not a start."""
    return client_name in SINGLE_INSTANCE


def _image_path(pid: int) -> str:
    """The executable a process is running, or ''.

    Opened with PROCESS_QUERY_LIMITED_INFORMATION, which is the right
    level for this and, unlike the older query right, is granted for a
    process the same user already owns -- so nothing here needs
    administrator rights.
    """
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                  False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def windowed_executables() -> list[str]:
    """The executable behind every visible top-level window.

    Separated from the matching below so the rule about which name counts
    can be tested without standing up windows, and so the enumeration can
    be tested against real ones.
    """
    if not IS_WINDOWS:
        return []
    paths = []

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            path = _image_path(pid.value)
            if path:
                paths.append(path)
        return True

    try:
        user32.EnumWindows(ENUM_PROC(visit), 0)
    except OSError as exc:  # noqa: BLE001 - a failed look is not an answer
        log.debug("Could not enumerate windows: %s", exc)
    return paths


def has_window(exe_path: str) -> bool:
    """Whether a visible top-level window belongs to *exe_path*.

    Matched on the executable rather than the process id: the id from
    `Popen` is the launcher that hands over and exits, not the instance
    that owns the window.

    Compared by file name, not by full path. Windows 11 ships several
    System32 executables as stubs that start a packaged copy living
    somewhere else entirely -- launch `notepad.exe` and the process that
    appears is running a different file, so a full-path comparison finds
    nothing and waits out the whole timeout for a window that is right
    there. The question being asked is "is a client of this kind up", and
    a second MobaXterm installation would serve the handoff just as well
    as the configured one, so the name is the honest thing to match.
    """
    if not IS_WINDOWS or not exe_path:
        return False
    wanted = os.path.normcase(os.path.basename(exe_path))
    return any(os.path.normcase(os.path.basename(path)) == wanted
               for path in windowed_executables())


def is_running(exe_path: str) -> bool:
    """Whether any process is running that executable.

    Asked instead of `has_window` before the first launch, because of the
    tray. MobaXterm can be closed to the notification area, where it has
    no visible window but is perfectly able to take a handoff. Judging by
    the window there would mean waiting the whole timeout for a window
    that is never going to appear, on every batch, for a user whose
    client was ready the entire time.

    Once the batch has decided it does have to wait, the window is the
    right signal again: a client that was not running at all is starting
    from nothing, and the window going up is what says it has finished.
    """
    if not IS_WINDOWS or not exe_path:
        return False
    wanted = os.path.normcase(os.path.basename(exe_path))
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return False
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if os.path.normcase(entry.szExeFile) == wanted:
                return True
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snapshot)


def wait_needed(client_name: str, client_path: str) -> bool:
    """Whether the batch should wait before its second launch.

    False when the client starts a process per session, and false when a
    single-instance client is already running -- the common case, where
    waiting would add a delay for nothing.
    """
    if not IS_WINDOWS or not is_single_instance(client_name):
        return False
    return not is_running(client_path)
