"""What happens between the shortcut and the keystrokes.

Five checks stand between a key press and a password appearing
somewhere. Each one has a way of being quietly dropped in a refactor,
and each one is the only thing preventing a specific bad outcome:

* the vault is locked        → nothing to send
* our own window is in front → typing the password into the search box
* nothing matched            → typing into a window nobody claimed
* the window would not come  → typing into whatever took its place
* the window changed midway  → the password half landing elsewhere

The Windows layer is replaced here, so nothing is actually typed.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _entry(**over):
    base = {"id": "1", "title": "GitHub", "username": "eslam",
            "password": "s3cret", "url": "github.com", "category": "General"}
    base.update(over)
    return base


@pytest.fixture
def controller(app_autotype):
    """The module the app is bound to — see the fixture for why not a
    plain import."""
    return app_autotype


@pytest.fixture
def typed(app, controller, monkeypatch):
    """Auto-type with the Windows half replaced by a recorder."""
    sent = {"steps": None, "values": None, "refocused": [], "alerts": [],
            "picker": []}

    monkeypatch.setattr(controller.autotype_win, "refocus",
                        lambda h: sent["refocused"].append(h) or True)

    def perform(steps, values, still_ok=None):
        sent["steps"] = steps
        sent["values"] = values
        return True

    monkeypatch.setattr(controller.autotype_win, "perform", perform)
    monkeypatch.setattr(app, "_alert",
                        lambda title, body="", **k: sent["alerts"].append(title))
    monkeypatch.setattr(app, "show_autotype_picker",
                        lambda *a: sent["picker"].append(a))
    # Run the send inline: a thread would race every assertion below.
    monkeypatch.setattr(controller.threading, "Thread",
                        lambda target, **k: type(
                            "Now", (), {"start": lambda _s: target()})())
    app.data["entries"] = [_entry()]
    return app, sent


def _in_front(controller, monkeypatch, handle, title):
    monkeypatch.setattr(controller.autotype_win, "foreground",
                        lambda: (handle, title))


class TestItRefusesToType:
    def test_when_the_vault_is_locked(self, typed, controller, monkeypatch):
        app, sent = typed
        _in_front(controller, monkeypatch, 4242, "GitHub — Chrome")
        app.key = None
        try:
            app.autotype.pressed(controller.FULL)
        finally:
            app.key = b"0" * 44
        assert sent["steps"] is None, "typed with the vault locked"

    def test_when_our_own_window_is_in_front(self, typed, controller,
                                             monkeypatch):
        """Otherwise the shortcut types the password into the vault's own
        search box, in front of whoever is looking at the screen.

        The handle fed in is the one Windows would actually report, not
        `winfo_id()`. The first version of this test used `winfo_id()`
        directly and passed while the guard was broken: Tk wraps its
        toplevels, so the two are different numbers, and the check found
        nothing. The test agreed with the code because it shared the
        code's wrong assumption.
        """
        app, sent = typed
        real = controller.autotype_win.top_level(int(app.root.winfo_id()))
        assert real != int(app.root.winfo_id()) or not             controller.autotype_win.available(),             "expected Tk's wrapper to differ from winfo_id on Windows"
        _in_front(controller, monkeypatch, real, "Password Vault")
        app.autotype.pressed(controller.FULL)
        assert sent["steps"] is None, "typed into our own window"

    def test_a_window_that_is_not_ours_is_not_mistaken_for_one(
            self, typed, controller, monkeypatch):
        """The opposite failure: a guard so eager it never types at all."""
        app, sent = typed
        _in_front(controller, monkeypatch, 12345, "Sign in · GitHub — Chrome")
        app.autotype.pressed(controller.FULL)
        assert sent["steps"], "refused a window that was not ours"

    def test_when_there_is_no_foreground_window(self, typed, controller, monkeypatch):
        app, sent = typed
        _in_front(controller, monkeypatch, 0, "")
        app.autotype.pressed(controller.FULL)
        assert sent["steps"] is None

    def test_when_the_window_will_not_come_back(self, typed, controller, monkeypatch):
        """Refocus is advisory — the shell can refuse it. Typing anyway
        sends the password to whatever took the foreground instead."""
        app, sent = typed
        monkeypatch.setattr(controller.autotype_win, "refocus",
                            lambda h: False)
        app.autotype.send(_entry(), 4242, controller.FULL)
        assert sent["steps"] is None
        # The message comes back through the handoff queue, because the
        # worker thread may not touch Tk itself.
        app.autotype._pump()
        assert sent["alerts"], "failed silently"

    def test_a_broken_sequence_is_refused_before_focus_moves(
            self, typed, controller, monkeypatch):
        app, sent = typed
        app.autotype.send(_entry(autotype_sequence="{NOPE}"), 42,
                          controller.FULL)
        assert sent["steps"] is None
        assert sent["refocused"] == [], "took the focus for nothing"
        assert sent["alerts"]


class TestItAsksWhenUnsure:
    def test_nothing_matches(self, typed, controller, monkeypatch):
        app, sent = typed
        _in_front(controller, monkeypatch, 4242, "Untitled — Notepad")
        app.autotype.pressed(controller.FULL)
        assert sent["picker"], "typed into an unmatched window"
        assert sent["steps"] is None

    def test_two_accounts_on_the_same_site(self, typed, controller, monkeypatch):
        app, sent = typed
        app.data["entries"] = [_entry(id="1", username="personal"),
                               _entry(id="2", username="work")]
        _in_front(controller, monkeypatch, 4242, "GitHub — Chrome")
        app.autotype.pressed(controller.FULL)
        assert sent["picker"], "guessed between two accounts"

    def test_the_picker_is_told_which_window(self, typed, controller, monkeypatch):
        """It has to be remembered before the dialog steals the focus."""
        app, sent = typed
        _in_front(controller, monkeypatch, 777, "Untitled — Notepad")
        app.autotype.pressed(controller.FULL)
        handle, title, which = sent["picker"][0]
        assert handle == 777
        assert title == "Untitled — Notepad"
        assert which == controller.FULL


class TestItTypes:
    def test_a_confident_match(self, typed, controller, monkeypatch):
        app, sent = typed
        _in_front(controller, monkeypatch, 4242, "Sign in · GitHub — Chrome")
        app.autotype.pressed(controller.FULL)
        assert sent["steps"], "did not type on a confident match"
        assert sent["values"]["username"] == "eslam"
        assert sent["values"]["password"] == "s3cret"

    def test_it_returns_to_the_right_window(self, typed, controller, monkeypatch):
        app, sent = typed
        _in_front(controller, monkeypatch, 4242, "GitHub — Chrome")
        app.autotype.pressed(controller.FULL)
        assert sent["refocused"] == [4242]

    def test_the_entry_sequence_is_used(self, typed, controller):
        app, sent = typed
        app.autotype.send(_entry(autotype_sequence="{USERNAME}{ENTER}"),
                          1, controller.FULL)
        assert sent["steps"] == [("field", "username"), ("key", "enter")]

    @pytest.mark.parametrize("which,expected", [
        ("username", [("field", "username")]),
        ("password", [("field", "password")]),
    ])
    def test_the_single_field_shortcuts_ignore_the_sequence(
            self, typed, controller, which, expected):
        """They exist to fill one box on a page asking for one thing.
        Running the whole sequence would defeat the point."""
        app, sent = typed
        app.autotype.send(
            _entry(autotype_sequence="{USERNAME}{TAB}{PASSWORD}{ENTER}"),
            1, which)
        assert sent["steps"] == expected


class TestWhatIsOffered:
    def test_matches_come_before_general_accounts(self, controller):
        match = _entry(id="m")
        general = _entry(id="g", url="", title="domain",
                         general_account=True)
        offered = controller.candidates("GitHub — Chrome", [general, match])
        assert [e["id"] for e, _why in offered] == ["m", "g"]

    def test_a_general_account_is_offered_with_nothing_else(self, controller):
        general = _entry(id="g", url="", title="domain",
                         general_account=True)
        offered = controller.candidates("Untitled — Notepad", [general])
        assert [e["id"] for e, _why in offered] == ["g"]

    def test_an_unrelated_entry_is_offered_last_and_unexplained(
            self, controller):
        """This test used to assert the opposite, and was green while the
        picker was unusable: with an unrelated entry excluded, a window
        that matched nothing offered only general accounts and no way to
        reach any other password. Ranking decides the order, not who is
        allowed in.
        """
        match = _entry(id="m", url="github.com")
        other = _entry(id="o", url="bank.example.com", title="Bank")
        offered = controller.candidates("GitHub — Chrome", [other, match])
        assert [e["id"] for e, _why in offered] == ["m", "o"]
        assert offered[-1][1] == "", "invented a reason for a non-match"

    def test_a_general_account_is_not_listed_twice(self, controller):
        """It can also match by pattern, and did once appear in both
        halves of the list."""
        both = _entry(id="g", url="", general_account=True,
                      match_patterns="notepad")
        offered = controller.candidates("Untitled — Notepad", [both])
        assert len(offered) == 1


class TestStartingUp:
    def test_nothing_registers_while_it_is_switched_off(self, app, controller):
        app.settings["autotype_enabled"] = False
        auto = controller.AutoType(app)
        auto.start()
        assert auto.listener is None

    def test_an_unreadable_shortcut_is_reported_not_crashed_on(self, app, controller):
        app.settings["autotype_enabled"] = True
        app.settings["autotype_hotkey_full"] = "nonsense+++"
        app.settings["autotype_hotkey_username"] = ""
        app.settings["autotype_hotkey_password"] = ""
        auto = controller.AutoType(app)
        assert auto.wanted() == {}
        assert auto.failures

    def test_an_empty_shortcut_is_simply_off(self, app, controller):
        app.settings["autotype_enabled"] = True
        for key in controller.SETTING_KEYS.values():
            app.settings[key] = ""
        auto = controller.AutoType(app)
        assert auto.wanted() == {}
        assert not auto.failures, "an unset shortcut is not a failure"


class TestLockingMidSequence:
    """A sequence can carry a delay, and auto-lock does not wait for it."""

    def test_the_guard_refuses_once_the_vault_locks(self, typed,
                                                    controller,
                                                    monkeypatch):
        app, _sent = typed
        seen = {}

        def perform(steps, values, still_ok=None):
            seen["before"] = still_ok()
            app.key = None
            seen["after"] = still_ok()
            return True

        monkeypatch.setattr(controller.autotype_win, "perform", perform)
        monkeypatch.setattr(controller.autotype_win, "foreground",
                            lambda: (99, "GitHub — Chrome"))
        try:
            app.autotype.send(_entry(), 99, controller.FULL)
        finally:
            app.key = b"0" * 44

        assert seen["before"] is True, "refused while unlocked"
        assert seen["after"] is False, \
            "would keep typing a password after the vault locked"

    def test_the_guard_also_refuses_a_changed_window(self, typed,
                                                    controller,
                                                    monkeypatch):
        app, _sent = typed
        seen = {}
        window = {"handle": 99}

        def perform(steps, values, still_ok=None):
            seen["before"] = still_ok()
            window["handle"] = 100
            seen["after"] = still_ok()
            return True

        monkeypatch.setattr(controller.autotype_win, "perform", perform)
        monkeypatch.setattr(controller.autotype_win, "foreground",
                            lambda: (window["handle"], "x"))
        app.autotype.send(_entry(), 99, controller.FULL)
        assert seen["before"] is True
        assert seen["after"] is False, \
            "would keep typing into whatever replaced the window"


class TestThePickerCanReachEverything:
    """Reported from real use: "only the accounts I marked global show
    up, nothing else appears".

    The first version stopped after matches and general accounts, and
    the picker's search filters that list — so on a window nothing
    claimed, every other password in the vault was unreachable. Ranking
    is a convenience. A picker the user opened on purpose has to be able
    to offer anything in the vault.
    """

    def test_an_unrelated_entry_is_still_offered(self, controller):
        plain = _entry(id="p", title="Bank", url="bank.example.com")
        offered = controller.candidates("Untitled — Notepad", [plain])
        assert [e["id"] for e, _why in offered] == ["p"], \
            "an ordinary entry could not be reached at all"

    def test_ordering_is_matches_then_general_then_the_rest(self,
                                                            controller):
        match = _entry(id="m", url="github.com")
        general = _entry(id="g", url="", title="domain",
                         general_account=True)
        other = _entry(id="o", url="bank.example.com", title="Bank")
        offered = controller.candidates("GitHub — Chrome",
                                        [other, general, match])
        assert [e["id"] for e, _why in offered] == ["m", "g", "o"]

    def test_the_rest_carry_no_invented_reason(self, controller):
        """A row that matched says why. A row that is merely in the vault
        has nothing to say, and inventing something would make the
        suggestions worth less."""
        other = _entry(id="o", url="bank.example.com", title="Bank")
        offered = controller.candidates("Untitled — Notepad", [other])
        assert offered[0][1] == ""

    def test_nothing_appears_twice(self, controller):
        """A general account can also match by pattern, and an entry
        reached three ways would have shown up three times."""
        both = _entry(id="b", url="github.com", general_account=True,
                      match_patterns="github")
        offered = controller.candidates("GitHub — Chrome", [both])
        assert len(offered) == 1

    def test_an_empty_vault_offers_nothing(self, controller):
        assert controller.candidates("GitHub — Chrome", []) == []
