"""Waiting for a single-instance client instead of guessing a delay.

Reported as "when I open three or four sessions, sometimes one opens,
sometimes two -- not the number I asked for", with no error anywhere.

The cause is that MobaXterm serves every tab from one process. After the
first launch, each `-newtab` is a handoff to an instance expected to be
running, and `subprocess.Popen` returns successfully whether that
instance is there or not. Start from a closed MobaXterm and the first
launch begins a cold start that takes seconds, while the handoffs behind
it -- spaced 400ms apart -- arrive at nothing.

Measured while working this out: with MobaXterm already running, four
launches 400ms apart all landed, four times out of four, including with a
real `ssh` in each tab. The spacing was never the problem. Being unable
to tell whether the client was up was.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from tests.conftest import requires_display

pytestmark = requires_display

MOBA = r"C:\Program Files (x86)\Mobatek\MobaXterm\MobaXterm.exe"
PUTTY = r"C:\Program Files\PuTTY\putty.exe"


@pytest.fixture
def clientready(app):
    """The module the running app is bound to.

    Not `import password_vault.clientready` at the top of the file. The
    app fixture clears `sys.modules` and builds its own copy, so a name
    imported at collection time points at a different module object --
    and patching it does nothing at all, in silence. The first version of
    this file did exactly that: the batch went on using the real check,
    found the MobaXterm running on this machine, decided nothing needed
    waiting for, and launched a second session while the test was
    asserting it had not. It failed for the one reason that had nothing
    to do with the code under test.

    `app_crypto`, `app_widgets` and `app_autotype` exist for the same
    trap.
    """
    import importlib

    return importlib.import_module("password_vault.clientready")


def _name(path):
    return os.path.normcase(os.path.basename(path))


def _entry(**over):
    base = {"id": "s1", "title": "web01", "username": "root",
            "password": "hunter2", "url": "10.0.0.5",
            "category": "Server"}
    base.update(over)
    return base


def _targets(count):
    return [{"entry": _entry(id=str(i), title=f"s{i}",
                             url=f"10.0.0.{i}"),
             "host": f"10.0.0.{i}", "user": "root", "port": 22}
            for i in range(count)]


def _pump(app, done, seconds=20):
    """Run the event loop until *done* or the deadline, whichever first."""
    deadline = time.monotonic() + seconds
    while not done() and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    return done()


class TestWhichClientsNeedWaitingFor:
    def test_mobaxterm_hands_off_to_one_instance(self, clientready):
        assert clientready.is_single_instance("MobaXterm")

    @pytest.mark.parametrize("name", ["PuTTY", "Windows SSH", "Kitty"])
    def test_the_others_start_a_process_each(self, clientready, name):
        assert not clientready.is_single_instance(name)

    def test_a_per_session_client_is_never_waited_for(self, clientready):
        """PuTTY opens its own window every time; there is nothing to
        wait for, and waiting would only add a delay."""
        assert not clientready.wait_needed("PuTTY", PUTTY)

    def test_a_running_client_is_not_waited_for(self, clientready,
                                                monkeypatch):
        monkeypatch.setattr(clientready, "is_running", lambda path: True)
        assert not clientready.wait_needed("MobaXterm", MOBA)

    def test_a_client_that_is_not_up_is(self, clientready, monkeypatch):
        monkeypatch.setattr(clientready, "IS_WINDOWS", True)
        monkeypatch.setattr(clientready, "is_running", lambda path: False)
        assert clientready.wait_needed("MobaXterm", MOBA)

    def test_a_client_in_the_tray_is_not_waited_for(self, clientready,
                                                    monkeypatch):
        """MobaXterm can be closed to the notification area, where it has
        no visible window and takes a handoff perfectly well. Deciding by
        the window would wait out the whole timeout, on every batch, for
        a window that is never going to appear."""
        monkeypatch.setattr(clientready, "IS_WINDOWS", True)
        monkeypatch.setattr(clientready, "is_running", lambda path: True)
        monkeypatch.setattr(clientready, "has_window", lambda path: False)
        assert not clientready.wait_needed("MobaXterm", MOBA)

    def test_nothing_is_waited_for_off_windows(self, clientready,
                                               monkeypatch):
        monkeypatch.setattr(clientready, "IS_WINDOWS", False)
        assert not clientready.wait_needed("MobaXterm", MOBA)


class TestSpottingTheWindow:
    @pytest.mark.parametrize("path", ["", r"C:\nowhere\absent.exe"])
    def test_nothing_is_found_for_what_is_not_running(self, clientready,
                                                      path):
        assert not clientready.has_window(path)

    def test_the_file_name_is_what_matches(self, clientready, monkeypatch):
        """Not the full path.

        Windows 11 ships System32 executables that are stubs for a
        packaged copy living elsewhere: launch `notepad.exe` and the
        process that appears is running a different file. Found the hard
        way -- the first version compared whole paths, and the check sat
        through its entire timeout waiting for a window that was already
        on screen.
        """
        monkeypatch.setattr(
            clientready, "windowed_executables",
            lambda: [r"C:\Windows\explorer.exe",
                     r"C:\Program Files\WindowsApps\M\MobaXterm.exe"])
        assert clientready.has_window(r"D:\Portable\MobaXterm.exe")
        assert not clientready.has_window(r"D:\Portable\putty.exe")

    def test_a_failed_enumeration_is_not_an_answer(self, clientready,
                                                   monkeypatch):
        """It reports "no window", which makes the batch wait rather than
        charge ahead -- and the wait gives up on its own."""
        monkeypatch.setattr(clientready, "windowed_executables",
                            lambda: [])
        assert not clientready.has_window(MOBA)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_a_process_is_seen_with_or_without_a_window(self, clientready):
        """Checked against processes that are certainly there and
        certainly not, rather than against a stub of itself."""
        assert clientready.is_running(r"C:\Windows\explorer.exe")
        assert clientready.is_running(sys.executable)
        assert not clientready.is_running(r"C:\x\zzz-not-a-program.exe")
        assert not clientready.is_running("")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_the_enumeration_finds_a_window_that_is_really_there(
            self, clientready, app):
        """Against a real window rather than a stub of one.

        The app under test owns a Tk window, so this interpreter is the
        answer -- which also means it is why the first version of the
        test below could never run: it skipped itself whenever this
        interpreter had a window, and under pytest it always does.
        """
        app.root.update()
        names = {_name(path)
                 for path in clientready.windowed_executables()}
        assert _name(sys.executable) in names, (
            "found no window for the interpreter running a visible Tk "
            "app, so the enumeration is not working at all")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_it_notices_a_window_appear_and_go(self, clientready,
                                               tmp_path, app):
        """The wait rests on this: a window that appears is spotted, and
        one that closes stops being reported.

        Counted rather than asked as yes/no. The app's own window means
        the answer to "does this interpreter have a window" is yes before
        the probe starts and yes after it goes, so only the change is
        visible -- and the change is what the wait actually reacts to.
        """
        probe = tmp_path / "probe.py"
        probe.write_text(
            "import tkinter, sys\n"
            "r = tkinter.Tk()\n"
            "r.title('clientready probe')\n"
            "r.geometry('160x60+40+40')\n"
            "r.after(int(sys.argv[1]), r.destroy)\n"
            "r.mainloop()\n", encoding="utf-8")

        me = sys.executable

        def windows_now():
            return sum(1 for path in clientready.windowed_executables()
                       if _name(path) == _name(me))

        before = windows_now()
        proc = subprocess.Popen([me, str(probe), "4000"])
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and windows_now() <= before:
                time.sleep(0.05)
            assert windows_now() > before, "never saw the window appear"
        finally:
            proc.wait(timeout=25)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and windows_now() > before:
            time.sleep(0.05)
        assert windows_now() == before, "still reporting a window that closed"


class TestTheBatchWaits:
    """What the user actually sees: the number of sessions asked for is
    the number that open."""

    @pytest.fixture
    def batch(self, app, monkeypatch):
        started = []
        monkeypatch.setattr(
            app, "_launch_ssh",
            lambda *a, **k: started.append(a[2]))
        from password_vault.ui.dialogs import bulk_ssh
        monkeypatch.setattr(bulk_ssh, "show_password_panel",
                            lambda *a, **k: None)
        yield app, started
        app.cancel_ssh_batch()

    def test_it_holds_after_the_first_until_the_client_is_up(
            self, batch, clientready, monkeypatch):
        app, started = batch
        up = {"yet": False}
        monkeypatch.setattr(clientready, "wait_needed",
                            lambda name, path: True)
        monkeypatch.setattr(clientready, "has_window",
                            lambda path: up["yet"])

        targets = _targets(4)
        app.launch_ssh_batch(targets, "MobaXterm", MOBA)

        # Long enough for several stagger intervals to have gone by.
        _pump(app, lambda: len(started) > 1, seconds=2)
        assert len(started) == 1, (
            f"{len(started)} sessions went out while the client was "
            "still starting; the rest of the handoffs are dropped")

        up["yet"] = True
        assert _pump(app, lambda: len(started) == len(targets)), \
            f"only {len(started)} of {len(targets)} opened"
        assert sorted(started) == sorted(t["host"] for t in targets)

    def test_a_client_already_running_is_not_waited_for(
            self, batch, clientready, monkeypatch):
        """The ordinary case. Waiting here would be a delay charged to
        every batch for a problem that is not happening."""
        app, started = batch
        monkeypatch.setattr(clientready, "is_running", lambda path: True)

        targets = _targets(3)
        app.launch_ssh_batch(targets, "MobaXterm", MOBA)
        assert _pump(app, lambda: len(started) == len(targets), seconds=5)

    def test_it_gives_up_waiting_and_opens_them_anyway(
            self, batch, clientready, monkeypatch):
        """A slow machine should mean a slow start, not sessions
        abandoned in silence. Being wrong about readiness costs a dropped
        tab; refusing costs the user the whole batch."""
        app, started = batch
        monkeypatch.setattr(clientready, "wait_needed",
                            lambda name, path: True)
        monkeypatch.setattr(clientready, "has_window", lambda path: False)
        monkeypatch.setattr(clientready, "READY_TIMEOUT_MS", 300)
        monkeypatch.setattr(clientready, "READY_POLL_MS", 50)

        targets = _targets(3)
        app.launch_ssh_batch(targets, "MobaXterm", MOBA)
        assert _pump(app, lambda: len(started) == len(targets),
                     seconds=10), \
            f"gave up entirely: only {len(started)} of {len(targets)}"

    def test_locking_mid_wait_stops_it(self, batch, clientready,
                                       monkeypatch):
        """The wait can last half a minute, which is long enough for
        auto-lock to arrive. A locked vault must not go on opening
        sessions for the entries it just dropped."""
        app, started = batch
        monkeypatch.setattr(clientready, "wait_needed",
                            lambda name, path: True)
        monkeypatch.setattr(clientready, "has_window", lambda path: False)
        monkeypatch.setattr(clientready, "READY_POLL_MS", 20)

        app.launch_ssh_batch(_targets(4), "MobaXterm", MOBA)
        assert len(started) == 1
        key, app.key = app.key, None
        try:
            _pump(app, lambda: False, seconds=1)
            assert len(started) == 1, "kept going with the vault locked"
        finally:
            app.key = key

    def test_a_per_session_client_still_goes_straight_through(self, batch):
        app, started = batch
        targets = _targets(4)
        app.launch_ssh_batch(targets, "PuTTY", PUTTY)
        assert len(started) == 1, "all four went out at once"
        assert _pump(app, lambda: len(started) == len(targets), seconds=10)
