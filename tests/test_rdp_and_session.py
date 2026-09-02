"""Remote Desktop signing itself in, and not asking twice who you meant.

Both came from using the app: "in RDP it doesn't type the password and
connect", and "the small window shouldn't have to appear and the user
press Type — those are extra steps".

The second one is the more interesting fix. The app already knew which
entry the session was opened with, because the user picked it and pressed
Connect; matching a window title was being used to work out something it
had just been told.
"""

from __future__ import annotations

import time

import pytest

from password_vault import rdpcreds
from tests.conftest import requires_display

pytestmark = requires_display

SELFTEST_HOST = "pv-tests.invalid"


def _entry(**over):
    base = {"id": "r", "title": "fs01", "username": "CORP\\eslam",
            "password": "S3cret Pass!", "url": "10.0.0.9",
            "category": "Server"}
    base.update(over)
    return base


class TestTheCredentialItself:
    """Written through CredWriteW, not `cmdkey`: that tool takes the
    password on a command line, where every other process on the machine
    can read it out of the process list."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        yield
        rdpcreds.delete(SELFTEST_HOST)

    def test_it_can_be_written_read_and_removed(self):
        assert not rdpcreds.exists(SELFTEST_HOST)
        assert rdpcreds.write(SELFTEST_HOST, "CORP\\eslam", "S3cret!") == ""
        assert rdpcreds.exists(SELFTEST_HOST)
        assert rdpcreds.delete(SELFTEST_HOST)
        assert not rdpcreds.exists(SELFTEST_HOST)

    def test_deleting_reports_whether_it_worked(self):
        """Leaving a password in another process's store because a delete
        quietly failed is the failure that matters, and it is silent."""
        rdpcreds.write(SELFTEST_HOST, "u", "p")
        assert rdpcreds.delete(SELFTEST_HOST) is True
        assert rdpcreds.delete(SELFTEST_HOST) is True

    def test_it_is_stored_where_remote_desktop_looks(self):
        assert rdpcreds.target_for("10.0.0.9") == "TERMSRV/10.0.0.9"

    def test_it_does_not_survive_a_logoff(self):
        """Session persistence, so a crash cannot leave it behind."""
        assert rdpcreds.CRED_PERSIST_SESSION == 1


class TestUsernamesWindowsRefuses:
    """The error Windows gives is the number 2202. Saying that to a user
    is not an explanation."""

    @pytest.mark.parametrize("username,expected", [
        ("", "would ask regardless"),
        ("CORP\teslam", "tab or a line break"),
        ("user\nname", "tab or a line break"),
        (".\\eslam", "'.\\name'"),
    ])
    def test_the_reason_is_given_in_words(self, username, expected):
        problem = rdpcreds.check_username(username)
        assert problem and expected in problem, problem

    @pytest.mark.parametrize("username", [
        "eslam", "CORP\\eslam", "eslam@corp.local",
    ])
    def test_ordinary_usernames_are_accepted(self, username):
        assert rdpcreds.check_username(username) == ""


class TestLaunchingRdp:
    @pytest.fixture
    def rdp(self, app, monkeypatch):
        seen = {"popen": [], "staged": [], "alerts": []}
        monkeypatch.setattr(
            "subprocess.Popen",
            lambda cmd, **k: seen["popen"].append(cmd) or object())
        monkeypatch.setattr(
            app, "_stage_password_for_paste",
            lambda entry, **k: seen["staged"].append(entry))
        monkeypatch.setattr(app, "_alert",
                            lambda *a, **k: seen["alerts"].append(a))
        yield app, seen
        rdpcreds.delete(SELFTEST_HOST)

    def test_it_stores_the_credential_and_launches(self, rdp):
        app, seen = rdp
        app.launch_rdp(_entry(), SELFTEST_HOST, 3389)
        assert seen["popen"], "mstsc was not launched"
        assert "/v:" + SELFTEST_HOST in seen["popen"][0]
        assert seen["staged"] == [], \
            "put the password on the clipboard as well, for nothing"
        rdpcreds.delete(SELFTEST_HOST)

    def test_a_non_standard_port_is_passed_through(self, rdp):
        app, seen = rdp
        app.launch_rdp(_entry(), SELFTEST_HOST, 3390)
        assert f"/v:{SELFTEST_HOST}:3390" in seen["popen"][0]
        rdpcreds.delete(SELFTEST_HOST)

    def test_it_falls_back_to_the_clipboard_without_a_username(self, rdp):
        """Windows would ask anyway. A connection that opens and asks is
        better than one that does not open."""
        app, seen = rdp
        app.launch_rdp(_entry(username=""), SELFTEST_HOST, 3389)
        assert seen["popen"], "did not launch"
        assert seen["staged"], "no password anywhere: the user is stuck"

    def test_a_failed_launch_takes_the_credential_back(self, rdp,
                                                       monkeypatch):
        """A password left in the credential store after nothing even
        started is the worst of both."""
        app, seen = rdp

        def boom(cmd, **k):
            raise OSError("mstsc is missing")

        monkeypatch.setattr("subprocess.Popen", boom)
        app.launch_rdp(_entry(), SELFTEST_HOST, 3389)
        assert seen["alerts"], "failed silently"
        assert not rdpcreds.exists(SELFTEST_HOST), \
            "left the password in the credential store"


class TestRememberingWhichEntry:
    """The user said which entry when they pressed Connect. Working it
    out again from a window title is asking a question already answered."""

    def test_a_launched_session_is_remembered(self, app):
        entry = app.data["entries"][0]
        app.remember_session_entry(entry)
        assert app.recent_session_entry() is entry

    def test_it_is_forgotten_after_a_while(self, app, monkeypatch):
        """Long enough for a client to start and a prompt to appear;
        not so long that it is still guessing an hour later."""
        entry = app.data["entries"][0]
        app.remember_session_entry(entry)
        # Move the same clock forward. An earlier version of this test
        # used perf_counter() as the fake "now", which counts from an
        # arbitrary origin -- so the difference came out hugely negative
        # and the test passed nothing at all.
        later = time.time() + app.SESSION_MEMORY_SECONDS + 60
        monkeypatch.setattr(time, "time", lambda: later)
        assert app.recent_session_entry() is None

    def test_locking_forgets_it(self, app):
        """A locked vault has nothing to offer, and the reference points
        into data that has been dropped."""
        entry = app.data["entries"][0]
        app.remember_session_entry(entry)
        app.key = None
        try:
            assert app.recent_session_entry() is None
        finally:
            app.key = b"0" * 44

    def test_a_deleted_entry_is_not_offered(self, app):
        entry = app.data["entries"][0]
        app.remember_session_entry(entry)
        app.data["entries"] = [e for e in app.data["entries"]
                               if e is not entry]
        assert app.recent_session_entry() is None

    def test_nothing_remembered_is_nothing_offered(self, app):
        app._recent_session = None
        assert app.recent_session_entry() is None


class TestTheShortcutUsesIt:
    def test_it_types_without_opening_the_picker(self, app, app_autotype,
                                                 monkeypatch):
        """The complaint this came from: the small window appearing and
        the user pressing Type are steps they had already taken."""
        controller = app_autotype
        sent, picker = [], []
        monkeypatch.setattr(controller.autotype_win, "foreground",
                            lambda: (4242, "1. root@fs01 — MobaXterm"))
        monkeypatch.setattr(controller.autotype_win, "refocus",
                            lambda h: True)
        monkeypatch.setattr(controller.autotype_win, "perform",
                            lambda steps, values, still_ok=None:
                                sent.append(values) or True)
        monkeypatch.setattr(app, "show_autotype_picker",
                            lambda *a: picker.append(a))
        monkeypatch.setattr(controller.threading, "Thread",
                            lambda target, **k: type(
                                "Now", (), {"start": lambda _s: target()})())

        entry = _entry(title="nothing like the window title", url="")
        app.data["entries"] = [entry]
        app.remember_session_entry(entry)

        app.autotype.pressed(controller.PASSWORD_ONLY)
        assert picker == [], "asked again which entry the user meant"
        assert sent and sent[0]["password"] == entry["password"]

    def test_the_picker_still_opens_with_nothing_remembered(
            self, app, app_autotype, monkeypatch):
        controller = app_autotype
        picker = []
        monkeypatch.setattr(controller.autotype_win, "foreground",
                            lambda: (4242, "Some Unrelated Window"))
        monkeypatch.setattr(app, "show_autotype_picker",
                            lambda *a: picker.append(a))
        app.data["entries"] = [_entry(title="zz", url="")]
        app._recent_session = None
        app.autotype.pressed(controller.PASSWORD_ONLY)
        assert picker, "typed into a window with nothing to go on"
