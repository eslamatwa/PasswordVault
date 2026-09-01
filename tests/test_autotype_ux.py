"""Three things that were technically correct and still wrong to use.

None of these was a crash. Each answered the question "is this correct?"
with yes and the question "is this any use to the person in front of the
screen?" with no:

* a warning about a clash, followed by saving the clash anyway
* a freeze at the exact moment something was already going wrong
* a dialog repeated until the user learns to dismiss it unread

The tests exist because behaviour like this has no failing symptom to
notice later — it just quietly makes the app worse.
"""

from __future__ import annotations

import pytest

from password_vault import hotkeys
from tests.conftest import requires_display

pytestmark = requires_display


def _entry(**over):
    base = {"id": "1", "title": "GitHub", "username": "eslam",
            "password": "s3cret", "url": "github.com", "category": "General"}
    base.update(over)
    return base


class TestAClashIsRefusedNotJustReported:
    def test_clashes_returns_the_parts_not_a_sentence(self):
        """So the message can be translated. A sentence built inside
        hotkeys.py arrives in English whatever language the app is in."""
        found = hotkeys.clashes({"Full": "Ctrl+Alt+V",
                                 "Username": "alt+ctrl+v"})
        assert found is not None
        name, other, combo = found
        assert {name, other} == {"Full", "Username"}
        assert combo == "Ctrl+Alt+V", "the combination is not normalised"

    def test_no_clash_returns_none(self):
        assert hotkeys.clashes({"Full": "Ctrl+Alt+V",
                                "Username": "Ctrl+Alt+U"}) is None

    def test_the_settings_dialog_refuses_to_save(self, app):
        """Warning and then saving leaves one shortcut permanently dead
        while the user believes both were accepted."""
        import customtkinter as ctk

        # Set through the settings, which is where the dialog reads them
        # from. Editing the capture box would prove nothing: it is
        # read-only and only its key handler writes the variable that
        # actually gets saved.
        before = dict(app.settings)
        app.settings["autotype_hotkey_full"] = "Ctrl+Alt+V"
        app.settings["autotype_hotkey_username"] = "Ctrl+Alt+V"

        app.show_settings_dialog()
        app.root.update()
        dlg = app._grab_stack[-1]
        try:
            widgets = []

            def walk(w):
                widgets.append(w)
                for child in w.winfo_children():
                    walk(child)

            walk(dlg)
            save = [w for w in widgets if isinstance(w, ctk.CTkButton)
                    and "Save" in str(getattr(w, "_text", ""))]
            assert save, "no Save button"
            save[0].invoke()
            app.root.update()

            assert dlg.winfo_exists(), \
                "the dialog closed on a clash instead of refusing"
            errors = [str(getattr(w, "_text", "")) for w in widgets
                      if isinstance(w, ctk.CTkLabel)
                      and "⚠️" in str(getattr(w, "_text", ""))]
            assert errors, "nothing on screen explained the refusal"
        finally:
            for open_dlg in list(app._grab_stack):
                try:
                    open_dlg.destroy()
                except Exception:  # noqa: BLE001
                    pass
            app.root.update()
            app.settings.update(before)


class TestTheWarningStopsRepeating:
    """It is correct information delivered at the wrong frequency, and
    the result is people who dismiss dialogs without reading them."""

    @pytest.fixture
    def failing(self, app, monkeypatch):
        shown = []
        monkeypatch.setattr(app, "_alert",
                            lambda title, body="", **k: shown.append(title))
        monkeypatch.setattr(app.autotype, "start", lambda: None)
        app.autotype.failures = {"full": "another program owns it"}
        app._autotype_warned = False
        return app, shown

    def test_unlock_warns_once_per_run(self, failing):
        app, shown = failing
        app.restart_autotype(announce=False)
        app.restart_autotype(announce=False)
        app.restart_autotype(announce=False)
        assert len(shown) == 1, f"warned {len(shown)} times on unlock"

    def test_changing_the_setting_always_warns(self, failing):
        """There the user has just asked for it and is waiting to hear."""
        app, shown = failing
        app.restart_autotype(announce=False)
        app.restart_autotype(announce=True)
        app.restart_autotype(announce=True)
        assert len(shown) == 3

    def test_it_warns_again_after_the_problem_clears(self, failing,
                                                    monkeypatch):
        """Otherwise a conflict that comes back is never mentioned."""
        app, shown = failing
        app.restart_autotype(announce=False)
        assert len(shown) == 1

        app.autotype.failures = {}
        app.restart_autotype(announce=False)
        assert len(shown) == 1, "warned when there was nothing to warn about"

        app.autotype.failures = {"full": "taken again"}
        app.restart_autotype(announce=False)
        assert len(shown) == 2, "stayed quiet about a new conflict"


class TestRefocusIsOffTheUiThread:
    def test_a_refused_focus_does_not_block_the_caller(self, app,
                                                       app_autotype,
                                                       monkeypatch):
        """Asking for the window back waits on the shell for up to a
        fifth of a second. On the Tk thread that reads as the app
        hanging, at exactly the moment it should be explaining itself."""
        import time

        controller = app_autotype
        alerts = []
        monkeypatch.setattr(app, "_alert",
                            lambda *a, **k: alerts.append(a))

        def slow_refocus(_handle):
            time.sleep(0.25)
            return False

        monkeypatch.setattr(controller.autotype_win, "refocus",
                            slow_refocus)
        monkeypatch.setattr(controller.autotype_win, "perform",
                            lambda *a, **k: True)

        started = time.perf_counter()
        app.autotype.send(_entry(), 4242, controller.FULL)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.15, \
            f"send() blocked its caller for {elapsed * 1000:.0f}ms"

        deadline = time.monotonic() + 5
        while not alerts and time.monotonic() < deadline:
            app.autotype._pump()
            app.root.update()
            time.sleep(0.01)
        assert alerts, "the failure was never reported"

    def test_nothing_is_typed_when_the_window_will_not_come_back(
            self, app, app_autotype, monkeypatch):
        controller = app_autotype
        typed = []
        monkeypatch.setattr(app, "_alert", lambda *a, **k: None)
        monkeypatch.setattr(controller.autotype_win, "refocus",
                            lambda _h: False)
        monkeypatch.setattr(controller.autotype_win, "perform",
                            lambda *a, **k: typed.append(a) or True)
        app.autotype.send(_entry(), 4242, controller.FULL)

        import time
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.autotype._pump()
            app.root.update()
            time.sleep(0.01)
        assert typed == [], "typed into a window it could not reach"


class TestTkIsOnlyTouchedFromItsOwnThread:
    """The rule this project already knew, and this feature broke again.

    `root.after` from a worker raises "main thread is not in main loop"
    as soon as that loop is not running, and is unsafe even when it is —
    it happens to work rather than being allowed to. Everything a worker
    needs to say goes back through a queue the Tk thread drains.
    """

    def test_no_worker_function_touches_tk(self):
        import pathlib

        source = (pathlib.Path(__file__).resolve().parent.parent
                  / "password_vault" / "autotype.py").read_text(
            encoding="utf-8")
        for name in ("def work(", "def _from_thread("):
            start = source.index(name)
            body = source[start:start + 700]
            assert "root.after" not in body,                 f"{name} touches Tk from a worker thread"

    def test_handed_back_work_waits_for_the_tk_thread(self, app):
        ran = []
        app.autotype.hand_back(lambda: ran.append("yes"))
        assert ran == [], "ran before the Tk thread asked for it"
        app.autotype._pump()
        assert ran == ["yes"]
        app.autotype.stop()

    def test_one_failing_handoff_does_not_strand_the_rest(self, app):
        ran = []

        def boom():
            raise RuntimeError("no")

        app.autotype.hand_back(boom)
        app.autotype.hand_back(lambda: ran.append("after"))
        app.autotype._pump()
        assert ran == ["after"], "a raising handoff stopped the queue"
        app.autotype.stop()
