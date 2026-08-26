"""
Single-instance guard.

Two copies of the app each hold the whole vault in memory and each write it
back in full, so the one that saves last silently discards everything the
other one changed. The lock is taken before the UI starts.
"""

from __future__ import annotations

import logging
import os
import re
import sys

log = logging.getLogger("PasswordVault")

DEFAULT_LOCK_NAME = "Local\\PasswordVault-SingleInstance"
WINDOW_TITLE = "Password Vault"

_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9

# Held for the process lifetime; the OS releases both on exit.
_held: list = []


def _posix_lock_path(name: str) -> str:
    from .crypto import DATA_DIR
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return os.path.join(DATA_DIR, f"{safe}.lock")


def acquire(name: str = DEFAULT_LOCK_NAME) -> bool:
    """Claim the single-instance slot.

    Returns False when another instance already holds it. A failure to
    create the lock itself is not treated as a conflict: refusing to start
    because the guard is unavailable would be worse than running unguarded.
    """
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            log.warning("Single-instance mutex could not be created; "
                        "starting without the guard.")
            return True
        if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _held.append(handle)
        return True

    try:
        import fcntl
    except ImportError:
        log.warning("No file locking available; starting without the guard.")
        return True
    try:
        # An advisory flock is released by the kernel when the process dies,
        # so a crash cannot leave a stale lock behind.
        handle = open(_posix_lock_path(name), "w", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    _held.append(handle)
    return True


def focus_existing(window_title: str = WINDOW_TITLE) -> None:
    """Best-effort: bring the running instance's window forward."""
    if sys.platform != "win32":
        return
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, window_title)
    if not hwnd:
        return
    # Only un-minimize a mapped window. The main window is withdrawn while
    # the app runs as the floating widget, and forcing that one visible
    # would bypass Tk's own state tracking.
    if user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
