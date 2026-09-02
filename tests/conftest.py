"""Shared fixtures for tests that need a live application object.

The app is built once for the whole session and reset between tests rather
than rebuilt. Creating a Tk root per test exhausts the interpreter's Tcl
support after a few dozen roots, and the failure surfaces as an unrelated
"can't find init.tcl" much later in the run.
"""

from __future__ import annotations

import copy
import logging
import logging.handlers
import os
import re
import shutil
import sys
import tempfile
import tkinter as tk

import pytest

# Redirect APPDATA before anything imports the package.
#
# `password_vault/__init__.py` opens %APPDATA%/PasswordVault/vault.log at
# import time and attaches it to the root logger, and its guard means the
# first handler wins for the rest of the process. pytest imports this
# conftest before any test module, so this is the only point early enough
# to catch it -- doing it in a fixture is far too late.
#
# Without this the suite writes thousands of lines into the log of the
# copy the user actually runs, and rotation then throws away the real
# history. That log is the only record of anything a user reports, so
# filling it with test output destroys the evidence.
REAL_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
LOG_SANDBOX = tempfile.mkdtemp(prefix="pv-tests-")
os.environ["APPDATA"] = LOG_SANDBOX


# ─── Keep the windows off the user's screen ──────────────────
#
# These tests drive a real Tk application: a session-wide main window plus
# a Toplevel for every dialog under test. On a developer's machine that
# means windows appearing, taking focus and disappearing for the minutes a
# run takes, which is indistinguishable from the app misbehaving on its
# own -- it was reported as exactly that.
#
# The windows still have to be *mapped*, because several tests ask whether
# a card or a dialog is actually on screen. So they are mapped somewhere
# nobody is looking rather than hidden: the position in every geometry
# request is rewritten, the size is left alone, and the calls that pull a
# window to the front are made into no-ops for the duration of the run.
OFFSCREEN_AT = "+30000+30000"
_GEOMETRY = re.compile(r"^(?P<size>\d+x\d+)?(?P<pos>[+-]\d+[+-]\d+)?$")

_real_geometry = tk.Wm.wm_geometry
_real_attributes = tk.Wm.wm_attributes


def _offscreen_geometry(self, newGeometry=None, **kwargs):
    """Honour the requested size; ignore the requested position."""
    if isinstance(newGeometry, str):
        match = _GEOMETRY.match(newGeometry)
        if match:
            newGeometry = (match.group("size") or "") + OFFSCREEN_AT
    return _real_geometry(self, newGeometry, **kwargs)


def _no_topmost(self, *args, **kwargs):
    """`-topmost` on a test window puts it over whatever is being read."""
    if args and args[0] == "-topmost":
        return ""
    return _real_attributes(self, *args, **kwargs)


def _place_offscreen(window) -> None:
    try:
        _real_geometry(window, OFFSCREEN_AT)
    except tk.TclError:
        pass


def _offscreen_init(cls):
    """Move a window out of sight as soon as it is built.

    Rewriting `geometry` is not enough on its own: a window that never
    asks for a position gets one from the window manager, which put the
    dialogs in this app at the top left of the display.
    """
    original = cls.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _place_offscreen(self)

    __init__.__wrapped__ = original
    cls.__init__ = __init__


def _install_offscreen() -> None:
    tk.Wm.wm_geometry = _offscreen_geometry
    tk.Wm.geometry = _offscreen_geometry
    tk.Wm.wm_attributes = _no_topmost
    tk.Wm.attributes = _no_topmost
    # Raising and focusing are what make the windows impossible to ignore.
    # `focus_force` also steals the keyboard from whatever the person at
    # the machine is actually typing into.
    for name in ("lift", "tkraise", "focus_force"):
        setattr(tk.Misc, name, lambda self, *a, **k: None)
    import customtkinter as ctk

    for cls in (tk.Tk, tk.Toplevel, ctk.CTk, ctk.CTkToplevel):
        _offscreen_init(cls)


_install_offscreen()


def _display_available() -> bool:
    try:
        root = tk.Tk()
    except Exception:  # noqa: BLE001 - TclError, or a headless display
        return False
    root.destroy()
    return True


def _assert_log_is_sandboxed() -> None:
    """Fail loudly rather than quietly writing to the real log."""
    for handler in logging.getLogger().handlers:
        path = getattr(handler, "baseFilename", None)
        if path and not os.path.abspath(path).startswith(
                os.path.abspath(LOG_SANDBOX)):
            raise RuntimeError(
                "the test suite is logging to a real vault log: "
                f"{path}. Something imported password_vault before "
                "conftest redirected APPDATA.")


_assert_log_is_sandboxed()


HAS_DISPLAY = _display_available()

# Most of this suite drives a real Tk application, and without a display
# those tests skip. That is right on a headless machine and dangerous on
# a build server: a run where everything skipped is green, reports
# success, and has checked nothing -- the same shape as the three guards
# in this project that turned out to be testing nothing at all.
#
# So CI sets this, and a missing display becomes a failure with a name
# rather than several hundred quiet skips.
REQUIRE_DISPLAY = os.environ.get("PASSWORDVAULT_REQUIRE_DISPLAY") == "1"

if REQUIRE_DISPLAY and not HAS_DISPLAY:
    raise RuntimeError(
        "PASSWORDVAULT_REQUIRE_DISPLAY=1 is set but Tk cannot open a "
        "display. Every windowed test would skip and the run would pass "
        "while checking nothing.")

# Two marks, not one. The skipif is what lets the suite run on a machine
# with no display; the `display` marker is what lets CI run everything
# *else* on its own, quickly, and know it really did exclude the windowed
# tests rather than quietly skipping them.
def pytest_configure(config):
    """Declare the marker here rather than in a pytest.ini.

    Adding an ini file to this repo turned a passing suite into 535
    passes and 237 Tcl errors, reproducibly, three runs in a row -- the
    shared Tk root stopped being creatable partway through. Removing the
    file restored it. I could not explain the mechanism, and shipping a
    config file whose effect I cannot account for is worse than not
    having one: the marker only needs registering, and this registers
    it.
    """
    config.addinivalue_line(
        "markers",
        "display: drives a real Tk window, so it needs one. Run the rest "
        "with -m 'not display' -- a deselect is visible in the count, "
        "while a skip on a headless build server looks like success.")


requires_display = [
    pytest.mark.display,
    pytest.mark.skipif(not HAS_DISPLAY,
                       reason="no display available for Tk"),
]


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
_APP_WIDGETS = None
_APP_AUTOTYPE = None


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

    global _APP_CRYPTO, _APP_WIDGETS, _APP_AUTOTYPE
    _APP_CRYPTO = sys.modules["password_vault.crypto"]
    _APP_WIDGETS = sys.modules["password_vault.ui.widgets"]
    _APP_AUTOTYPE = sys.modules["password_vault.autotype"]

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
def app_widgets(_live_app):
    """The widgets module the running app actually uses.

    Same trap as `app_crypto`, and it bites harder here because the
    module holds caches. A test that imports `password_vault.ui.widgets`
    at collection time gets the copy from before `_live_app` cleared
    `sys.modules`, so it reads an empty pill cache while the app fills a
    different one — and concludes the cache is broken when it is fine.
    """
    assert _APP_WIDGETS is not None, "the app was never built"
    return _APP_WIDGETS


@pytest.fixture
def app_autotype(_live_app):
    """The auto-type module the running app is bound to.

    Same trap as `app_crypto` and `app_widgets`, and this one is easy to
    miss because the symptom is a test that simply does nothing: patches
    land on a second copy of the module while the app calls the first,
    so every check passes vacuously or fails for no visible reason.
    """
    assert _APP_AUTOTYPE is not None, "the app was never built"
    return _APP_AUTOTYPE


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
