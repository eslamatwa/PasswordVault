"""Wiring a hotkey to a keystroke, with the checks in between.

The order here is the whole safety argument, so it is written out rather
than left to be inferred from the code:

1. Is the vault unlocked? A locked vault has no passwords to send.
2. Which window is in front, and is it ours? Typing into our own search
   box is the one guaranteed-wrong target.
3. Does an entry match it confidently? If not, ask — never guess.
4. Put that window back in front, and *confirm* it came back.
5. Before every keystroke, check it is still the same window.

Step 5 is the one that is easy to leave out. A sequence takes a second
or two; if the user alt-tabs in the middle, the second half of a login
lands somewhere else. That half is usually the password.
"""

from __future__ import annotations

import logging
import queue
import threading

from . import autotype_win, hotkeys
from .i18n import t
from .autotype_match import choose, is_general, rank
from .autotype_sequence import DEFAULT, SequenceError, parse

log = logging.getLogger("PasswordVault")

# Which shortcut does what. The names are the keys the listener reports.
FULL = "full"
USERNAME_ONLY = "username"
PASSWORD_ONLY = "password"

SETTING_KEYS = {
    FULL: "autotype_hotkey_full",
    USERNAME_ONLY: "autotype_hotkey_username",
    PASSWORD_ONLY: "autotype_hotkey_password",
}

# What a single-field shortcut sends. Not the entry's own sequence: the
# point of these is to fill one box on a page that asks for one thing.
PARTIAL = {USERNAME_ONLY: "{USERNAME}", PASSWORD_ONLY: "{PASSWORD}"}


def candidates(title, entries):
    """Everything the picker can offer, best guesses first.

    Three bands, in order: entries that matched the window, general
    accounts, then the rest of the vault. Each is ``(entry, reason)``,
    and an entry in the last band has no reason -- there is nothing to
    say about it beyond being in the vault.

    The last band is the point. The first version stopped after the
    first two, so on a window nothing claimed the picker showed only
    entries flagged as general accounts and there was no way to reach any
    other password at all -- not even by typing its name, since the
    search filters this list. A picker the user opened deliberately has
    to be able to offer anything; ranking is a convenience, not a
    gate.
    """
    ranked = rank(title, entries)
    seen = {id(entry) for _points, entry, _why in ranked}
    out = [(entry, why) for _points, entry, why in ranked]

    for entry in entries or []:
        if is_general(entry) and id(entry) not in seen:
            out.append((entry, "a general account"))
            seen.add(id(entry))

    for entry in entries or []:
        if id(entry) not in seen:
            out.append((entry, ""))
    return out


class AutoType:
    """Owns the listener and decides what a press means."""

    # How often the Tk thread looks for work handed back by a worker.
    # Short enough that a hotkey press feels immediate, long enough that
    # an idle vault is not waking up constantly.
    PUMP_MS = 40

    def __init__(self, app):
        self.app = app
        self.listener = None
        self.failures: dict[str, str] = {}
        # Tk may only be touched from the thread running its main loop.
        # `root.after` from anywhere else raises "main thread is not in
        # main loop" when that loop is not running, and is unsafe even
        # when it is -- it happens to work rather than being allowed to.
        # Both the hotkey listener and the typing worker hand their
        # results over through here instead.
        self._handoff: queue.Queue = queue.Queue()
        self._pump_id = None

    # ── starting and stopping ──
    def wanted(self) -> dict:
        """The shortcuts that are configured and readable."""
        combos = {}
        for name, key in SETTING_KEYS.items():
            text = (self.app.settings.get(key) or "").strip()
            if not text:
                continue
            try:
                combos[name] = hotkeys.parse(text)
            except hotkeys.HotkeyError as exc:
                self.failures[name] = str(exc)
                log.warning("Auto-type shortcut %s is unusable: %s",
                            name, exc)
        return combos

    def start(self) -> None:
        self.stop()
        self.failures = {}
        if not self.app.settings.get("autotype_enabled", False):
            return
        if not autotype_win.available():
            return
        combos = self.wanted()
        if not combos:
            return
        self.listener = autotype_win.HotkeyListener(self._from_thread)
        self.listener.start(combos)
        if self._pump_id is None:
            self._pump()
        self.failures.update(self.listener.failures)
        if self.listener.failures:
            log.warning("Auto-type could not register: %s",
                        ", ".join(self.listener.failures))

    def stop(self) -> None:
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self._pump_id is not None:
            try:
                self.app.root.after_cancel(self._pump_id)
            except Exception:  # noqa: BLE001 - already gone
                pass
            self._pump_id = None

    # ── a press ──
    def hand_back(self, work) -> None:
        """Queue *work* to run on the Tk thread. Safe from any thread."""
        self._handoff.put(work)

    def _pump(self) -> None:
        """Run whatever the workers left, on the Tk thread."""
        while True:
            try:
                work = self._handoff.get_nowait()
            except queue.Empty:
                break
            try:
                work()
            except Exception:  # noqa: BLE001 - one failure must not
                # stop the pump and strand everything after it.
                log.exception("Auto-type handoff failed.")
        try:
            self._pump_id = self.app.root.after(self.PUMP_MS, self._pump)
        except Exception:  # noqa: BLE001 - the root is going away
            self._pump_id = None

    def _from_thread(self, which: str) -> None:
        """Called on the listener thread; hand it to Tk's."""
        self.hand_back(lambda: self.pressed(which))

    def pressed(self, which: str) -> None:
        if self.app.key is None or not self.app.data:
            log.info("Auto-type ignored: the vault is locked.")
            return
        handle, title = autotype_win.foreground()
        if not handle:
            return
        if self._is_ours(handle):
            # Otherwise the shortcut types the password into the vault's
            # own search box, in front of whoever is looking.
            log.info("Auto-type ignored: our own window is in front.")
            return

        entries = self.app.data.get("entries", [])
        entry = choose(title, entries)
        if entry is None:
            self.app.show_autotype_picker(handle, title, which)
            return
        self.send(entry, handle, which)

    def _is_ours(self, handle: int) -> bool:
        """Is the window in front one of ours?

        Compared at the top level on both sides. `winfo_id()` returns the
        inner HWND that Tk wraps, never the one `GetForegroundWindow`
        reports, so matching the two raw values finds nothing and this
        guard quietly never fires -- letting the shortcut type the
        password into the vault's own search box.
        """
        wanted = autotype_win.top_level(handle)
        own = set()
        for widget in (self.app.root,) + tuple(
                self.app.root.winfo_children()):
            try:
                own.add(autotype_win.top_level(int(widget.winfo_id())))
            except Exception:  # noqa: BLE001 - destroyed mid-iteration
                continue
        return wanted in own

    def sequence_for(self, entry, which: str) -> str:
        if which in PARTIAL:
            return PARTIAL[which]
        return (entry.get("autotype_sequence") or "").strip() or DEFAULT

    def send(self, entry, handle: int, which: str) -> None:
        """Type *entry* into the window *handle*, if it is still safe."""
        try:
            steps = parse(self.sequence_for(entry, which))
        except SequenceError as exc:
            self.app._alert(t("Auto-type"), f"{exc}")
            return

        values = {
            "username": entry.get("username", ""),
            "password": entry.get("password", ""),
            "url": entry.get("url", ""),
            "title": entry.get("title", ""),
        }

        def still_ok():
            # ctypes and a plain attribute read, so this is safe to call
            # from the worker thread.
            if autotype_win.foreground()[0] != handle:
                return False
            # The vault locking mid-sequence has to stop it too. A
            # sequence can contain a delay, and auto-lock does not wait
            # for one: without this, a vault that locked five seconds ago
            # still finishes typing the password it captured beforehand.
            return self.app.key is not None

        def refused():
            self.app._alert(
                t("Auto-type"),
                t("Could not return to that window, so nothing was "
                  "typed."))

        def work():
            # Asking for the window back waits for the shell to agree,
            # up to a fifth of a second. On the Tk thread that is a
            # visible freeze, and it happens precisely when something is
            # already going wrong -- so the failure reads as the app
            # hanging rather than as a message.
            if not autotype_win.refocus(handle):
                self.hand_back(refused)
                return
            ok = autotype_win.perform(steps, values, still_ok)
            log.info("Auto-type into %r: %s", entry.get("title", ""),
                     "done" if ok else "stopped early")

        # On a worker thread: a sequence with a delay in it would
        # otherwise freeze the UI for as long as the delay, and the app
        # is not the window being typed into anyway.
        threading.Thread(target=work, daemon=True,
                         name="autotype-send").start()
