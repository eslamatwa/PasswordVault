"""Shared fixtures for tests that need a live application object.

The app is built once for the whole session and reset between tests rather
than rebuilt. Creating a Tk root per test exhausts the interpreter's Tcl
support after a few dozen roots, and the failure surfaces as an unrelated
"can't find init.tcl" much later in the run.
"""

from __future__ import annotations

import copy
import os
import shutil
import sys
import tempfile
import tkinter as tk

import pytest


def _display_available() -> bool:
    try:
        root = tk.Tk()
    except Exception:  # noqa: BLE001 - TclError, or a headless display
        return False
    root.destroy()
    return True


HAS_DISPLAY = _display_available()

requires_display = pytest.mark.skipif(
    not HAS_DISPLAY, reason="no display available for Tk")


SAMPLE_VAULT = {
    "categories": ["General", "Work", "Server"],
    "entries": [
        {"id": "e1", "title": "Bank", "username": "user@example.com",
         "password": "Str0ng!Passw0rd", "url": "https://bank.example.com",
         "category": "General", "notes": "note", "color": "blue",
         "pinned": True, "created_at": "2024-01-01T00:00:00",
         "modified_at": "2024-01-01T00:00:00"},
        {"id": "e2", "title": "db01", "username": "root",
         "password": "weak", "url": "10.0.0.5", "category": "Server",
         "notes": "", "color": "default", "pinned": False,
         "created_at": "2024-01-01T00:00:00",
         "modified_at": "2024-01-01T00:00:00"},
    ],
    "trash": [
        {"id": "t1", "title": "Old Account", "username": "u",
         "password": "p", "category": "Work",
         "deleted_at": "2024-06-01T00:00:00"},
    ],
}

# Placeholder key: these tests stub the save path, so it is never used to
# encrypt anything. It is the right length for a Fernet key regardless.
FAKE_KEY = b"0" * 44


# The crypto module the running app is bound to, captured while it is
# built. Several test modules reload password_vault.crypto against their
# own temp APPDATA and leave the reloaded copy in sys.modules, so a test
# that imports it later can get a module whose DATA_FILE points at a
# directory that no longer exists — and not the one the app reads and
# writes. Anything that has to touch the app's real files must go through
# the `app_crypto` fixture rather than a fresh import.
_APP_CRYPTO = None


@pytest.fixture(scope="session")
def _live_app():
    if not HAS_DISPLAY:
        pytest.skip("no display available for Tk")
    tmp = tempfile.mkdtemp()
    previous = os.environ.get("APPDATA")
    os.environ["APPDATA"] = tmp
    for mod in [m for m in list(sys.modules)
                if m == "main" or m.startswith("password_vault")]:
        sys.modules.pop(mod, None)

    import main as main_module

    global _APP_CRYPTO
    _APP_CRYPTO = sys.modules["password_vault.crypto"]

    vault = main_module.PasswordVault()
    # The real save path needs a working key and a writable vault file;
    # every dialog under test only cares that saving reports success.
    vault._save_guarded = lambda: True
    try:
        yield vault
    finally:
        try:
            vault.root.destroy()
        except Exception:  # noqa: BLE001 - already torn down
            pass
        if previous is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = previous
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def app(_live_app):
    """An unlocked PasswordVault, reset to a known state for each test.

    The vault is unlocked by hand rather than through the login screen: the
    point of these tests is what the dialogs do once the app is running.
    """
    _reset(_live_app)
    yield _live_app
    _close_dialogs(_live_app)


@pytest.fixture
def app_crypto(_live_app):
    """The crypto module the running app actually uses.

    Not `import password_vault.crypto` — by the time a test runs, that name
    may point at a copy another test module reloaded against its own temp
    directory. Using the wrong one is silent: writes land somewhere the app
    never looks, and the test fails for a reason that has nothing to do
    with what it is checking.
    """
    assert _APP_CRYPTO is not None, "the app was never built"
    return _APP_CRYPTO


@pytest.fixture
def arabic(app):
    """Switch the app to Arabic (RTL) for the duration of one test.

    The window is rebuilt because Tk resolves anchor, justify, pack side
    and padding when a widget is created — the same reason the Settings
    dialog rebuilds on a language change.
    """
    from password_vault import i18n

    i18n.set_language("Arabic")
    app._rebuild_ui()
    app.root.update()
    try:
        yield app
    finally:
        i18n.set_language("English")
        try:
            app._rebuild_ui()
            app.root.update()
        except Exception:  # noqa: BLE001 - torn down mid-test
            pass


def _close_dialogs(vault) -> None:
    for child in list(vault.root.winfo_children()):
        if isinstance(child, tk.Toplevel):
            try:
                child.grab_release()
                child.destroy()
            except tk.TclError:
                pass
    vault._grab_stack.clear()
    try:
        vault.root.grab_release()
        vault.root.update_idletasks()
    except tk.TclError:
        pass


def _reset(vault) -> None:
    """Return the app to a freshly-unlocked state between tests."""
    _close_dialogs(vault)
    for timer in ("_idle_timer", "_save_timer", "_search_after_id",
                  "_clipboard_timer"):
        handle = getattr(vault, timer, None)
        if handle:
            try:
                vault.root.after_cancel(handle)
            except (tk.TclError, ValueError):
                pass
            setattr(vault, timer, None)

    if vault.mini_vault is not None:
        try:
            vault.mini_vault.destroy()
        except tk.TclError:
            pass
        vault.mini_vault = None
    if vault.floating_widget is not None:
        try:
            vault.floating_widget.destroy()
        except tk.TclError:
            pass
        vault.floating_widget = None

    vault.key = FAKE_KEY
    vault.data = copy.deepcopy(SAMPLE_VAULT)
    vault.current_category = "All"

    # A previous test may have locked the vault, which tears the main frame
    # down and puts the login screen back up.
    login = getattr(vault, "login_frame", None)
    if login is not None:
        try:
            if login.winfo_exists():
                login.destroy()
        except tk.TclError:
            pass
        vault.login_frame = None
    if vault._main_frame is not None:
        try:
            if vault._main_frame.winfo_exists():
                vault._main_frame.destroy()
        except tk.TclError:
            pass
        vault._main_frame = None

    vault.build_ui()
    vault.root.update_idletasks()
