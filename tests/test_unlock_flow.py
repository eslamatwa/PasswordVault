"""The unlock path end to end, with nothing stubbed.

Real PBKDF2, real Fernet, real files. This is what a user does every time
they open the app, and since the derivation moved to a worker thread it is
worth exercising whole rather than in pieces.

The interrupted-rotation case is here rather than only in
test_rotation_journal.py because recovery is a property of the *unlock*,
not of the crypto helpers: the login screen has to try both salts and then
finish the rotation the failed password change left behind.
"""

from __future__ import annotations

import os
import time
import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display

MASTER = "CorrectHorse1!x"
ROTATED = "AnotherHorse2!y"
WRONG = "TotallyWrong9!z"


@pytest.fixture
def blank_vault(app, app_crypto):
    """A real, empty vault directory for the duration of one test.

    The shared app's APPDATA persists for the session, so anything written
    here is removed afterwards — otherwise the next test would find a vault
    where it expected a first run.
    """
    import types

    import main as main_module

    crypto = app_crypto
    paths = [crypto.DATA_FILE, crypto.SALT_FILE, crypto.ROTATION_FILE]

    def clear():
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass

    # The shared fixture stubs saving, which every other test wants. Here
    # it would mean the vault file is never written, so `is_new` stays true
    # and any password appears to work.
    stub = app._save_guarded
    app._save_guarded = types.MethodType(
        main_module.PasswordVault._save_guarded, app)

    # Put the app into a locked state with no vault on disk, without going
    # through _auto_lock. The login screen decides whether this is a first
    # run when it is built, so it has to be built *after* the files are
    # gone — and nothing here may depend on state an earlier test left
    # behind, which is what made this order-dependent the first time.
    app._save_pending = False
    app._save_failure_reported = False
    clear()
    app.key = None
    app.data = None
    for attr in ("_main_frame", "login_frame"):
        frame = getattr(app, attr, None)
        if frame is not None:
            try:
                if frame.winfo_exists():
                    frame.destroy()
            except tk.TclError:
                pass
            setattr(app, attr, None)
    app.show_login()
    app.root.update()
    assert app.confirm_entry is not None, \
        "the login screen should be offering to create a vault"
    try:
        yield app
    finally:
        app._save_guarded = stub
        clear()


def _pump_until(app, predicate, timeout=120):
    """Run Tk's loop until *predicate* holds.

    mainloop() rather than update(): the worker marshals its result with
    root.after(), which Tk accepts from another thread only while the main
    thread is inside mainloop — the state the real app is always in.

    The timeout is generous on purpose. It exists to stop a hung worker
    from wedging the run, not to assert anything about speed: a tighter
    one made these tests fail late in a loaded suite for the machine's
    reasons rather than the code's.
    """
    deadline = time.time() + timeout

    def poll():
        if predicate() or time.time() > deadline:
            app.root.quit()
        else:
            app.root.after(20, poll)

    app.root.after(20, poll)
    app.root.mainloop()
    return predicate()


def _attempt(app, password):
    app.master_entry.delete(0, "end")
    app.master_entry.insert(0, password)
    if app.confirm_entry is not None:
        app.confirm_entry.delete(0, "end")
        app.confirm_entry.insert(0, password)
    app.unlock()
    assert _pump_until(app, lambda: not app._unlocking), \
        "the unlock worker never reported back"


def test_create_lock_and_reopen_a_real_vault(blank_vault, app_crypto):
    crypto = app_crypto
    app = blank_vault
    _attempt(app, MASTER)
    assert app.key is not None, "the vault was not created"
    assert os.path.exists(crypto.DATA_FILE)

    app.data["entries"].append({
        "id": "e1", "title": "Bank", "username": "u",
        "password": "s3cret", "url": "", "category": "General",
        "notes": "", "color": "default", "pinned": False,
        "created_at": "2024-01-01T00:00:00",
        "modified_at": "2024-01-01T00:00:00"})
    crypto.save_data(app.data, app.key)

    app._auto_lock()
    app.root.update()
    assert app.key is None

    _attempt(app, MASTER)
    assert app.key is not None
    assert app.data["entries"][0]["title"] == "Bank"


def test_a_wrong_password_is_refused_and_leaves_no_key(blank_vault):
    app = blank_vault
    _attempt(app, MASTER)
    app._auto_lock()
    app.root.update()

    _attempt(app, WRONG)

    assert app.key is None, "a wrong password unlocked the vault"
    assert app.data is None
    assert app.error_label.cget("text"), "no error was shown"
    # The key must not survive a failed attempt: while it did, the idle
    # timer stayed armed on the login screen and auto-lock later stacked a
    # second login frame over the first.
    assert app._idle_timer is None


def test_an_interrupted_rotation_opens_with_the_new_password(
        blank_vault, app_crypto):
    """The failure that used to leave a vault no password could open."""
    crypto = app_crypto
    app = blank_vault
    _attempt(app, MASTER)
    data = app.data
    app._auto_lock()
    app.root.update()

    # The state a failed master-password change leaves behind: the vault is
    # written under the new key, the salt file still holds the old one, and
    # the rollback never landed.
    new_salt = os.urandom(32)
    crypto.begin_rotation(new_salt)
    crypto.save_data(data, crypto.derive_key(ROTATED, new_salt))
    assert len(crypto.candidate_salts()) == 2

    _attempt(app, ROTATED)

    assert app.key is not None, "the interrupted rotation was unrecoverable"
    # The unlock also finishes what the change started.
    assert not os.path.exists(crypto.ROTATION_FILE)
    assert len(crypto.candidate_salts()) == 1


def test_the_old_password_no_longer_works_after_recovery(
        blank_vault, app_crypto):
    crypto = app_crypto
    app = blank_vault
    _attempt(app, MASTER)
    data = app.data
    app._auto_lock()
    app.root.update()

    new_salt = os.urandom(32)
    crypto.begin_rotation(new_salt)
    crypto.save_data(data, crypto.derive_key(ROTATED, new_salt))
    _attempt(app, ROTATED)
    app._auto_lock()
    app.root.update()

    _attempt(app, MASTER)
    assert app.key is None, "the superseded password still opens the vault"
