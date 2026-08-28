"""Opening several SSH sessions at once.

The launching is the easy half. The half worth testing is what happens
around it: which entries qualify, that a bad host is refused rather than
quietly reshaped, that ten launches do not land in the same instant, and
that the panel holding ten passwords does not outlive the lock.
"""

from __future__ import annotations

import time
import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _entry(**over):
    base = {"id": "s1", "title": "web01", "username": "root",
            "password": "hunter2", "url": "10.0.0.5",
            "category": "Server", "notes": "", "color": "default",
            "pinned": False, "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-01T00:00:00"}
    base.update(over)
    return base


def _servers(app, entries):
    app.data["entries"] = entries
    app.refresh_entries()
    app.root.update()


@pytest.fixture
def bulk(app):
    """The dialog module, with any batch it starts stopped afterwards.

    A batch plays out over seconds through chained `after` callbacks. One
    left running at the end of a test fires into the *next* test, which
    is how the leak below was found: launches from an earlier test turned
    up in a later test's list of hosts.
    """
    from password_vault.ui.dialogs import bulk_ssh
    yield bulk_ssh
    app.cancel_ssh_batch()


class TestWhatQualifies:
    def test_a_server_category_entry_is_offered(self, app, bulk):
        _servers(app, [_entry()])
        targets = bulk.collect_targets(app)
        assert [x["entry"]["title"] for x in targets] == ["web01"]
        assert targets[0]["host"] == "10.0.0.5"
        assert targets[0]["user"] == "root"

    def test_a_webmail_entry_is_not(self, app, bulk):
        """Same rule as the right-click menu: a plain web address is not
        a machine to log into, or every entry with a URL would show up."""
        _servers(app, [_entry(url="https://mail.example.com/login",
                              category="General")])
        assert bulk.collect_targets(app) == []

    def test_the_list_matches_the_menu_exactly(self, app, bulk):
        """An entry that offers 'SSH Session ...' individually but is
        missing from this list would look like a bug in the list."""
        entries = [
            _entry(id="a", title="db", url="10.0.0.6"),
            _entry(id="b", title="mail", url="https://m.example.com/x",
                   category="General"),
            _entry(id="c", title="jump", url="ssh://jump.example.com"),
            _entry(id="d", title="note", url="", category="General"),
        ]
        _servers(app, entries)
        offered = {e["title"] for e in entries
                   if app._looks_remote(e, e.get("url", ""))}
        listed = {x["entry"]["title"] for x in bulk.collect_targets(app)}
        assert listed == offered

    def test_an_ssh_url_keeps_its_port(self, app, bulk):
        _servers(app, [_entry(url="ssh://box.example.com:2222")])
        assert bulk.collect_targets(app)[0]["port"] == 2222

    def test_the_list_is_sorted_by_title(self, app, bulk):
        _servers(app, [_entry(id="1", title="zeta", url="10.0.0.1"),
                       _entry(id="2", title="alpha", url="10.0.0.2")])
        titles = [x["entry"]["title"] for x in bulk.collect_targets(app)]
        assert titles == ["alpha", "zeta"]


class TestRefusals:
    def test_a_host_with_a_shell_character_is_flagged_not_fixed(
            self, app, bulk):
        """The single-session flow refuses these rather than stripping
        them, after stripping silently corrupted real logins. The batch
        has to refuse them the same way."""
        _servers(app, [_entry(url="10.0.0.5&calc")])
        target = bulk.collect_targets(app)[0]
        assert target["problem"], "a shell character was accepted"
        assert "10.0.0.5" in target["host"], \
            "the host was rewritten instead of refused"

    def test_a_username_with_a_shell_character_is_flagged(self, app, bulk):
        _servers(app, [_entry(username="root|whoami")])
        assert bulk.collect_targets(app)[0]["problem"]

    def test_an_ordinary_username_is_not_flagged(self, app, bulk):
        """`svc+deploy` is a real account name and used to be mangled."""
        _servers(app, [_entry(username="svc+deploy")])
        target = bulk.collect_targets(app)[0]
        assert not target["problem"]
        assert target["user"] == "svc+deploy"

    def test_an_entry_with_no_host_is_shown_with_a_reason(self, app, bulk):
        _servers(app, [_entry(url="", title="mystery")])
        target = bulk.collect_targets(app)[0]
        assert target["problem"], "an unusable entry was offered as usable"
        assert target["host"] == ""


class TestLaunching:
    def test_the_launches_are_spread_out(self, app, bulk, monkeypatch):
        """Ten Popen calls in the same millisecond makes a cold-starting
        MobaXterm drop tabs. Only the first should have gone out by the
        time the call returns."""
        calls = []
        monkeypatch.setattr(
            app, "_launch_ssh",
            lambda *a, **k: calls.append(a[3] or a[2]))
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)

        _servers(app, [_entry(id=str(i), title=f"s{i}",
                              url=f"10.0.0.{i}") for i in range(5)])
        app.launch_ssh_batch(bulk.collect_targets(app), "PuTTY", "putty.exe")
        assert len(calls) == 1, f"{len(calls)} launched at once"

    def test_they_all_arrive_eventually(self, app, bulk, monkeypatch):
        calls = []
        monkeypatch.setattr(app, "_launch_ssh",
                            lambda *a, **k: calls.append(a[2]))
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)

        _servers(app, [_entry(id=str(i), title=f"s{i}",
                              url=f"10.0.0.{i}") for i in range(4)])
        targets = bulk.collect_targets(app)
        app.launch_ssh_batch(targets, "PuTTY", "putty.exe")

        # Wait on the condition, not on a fixed number of milliseconds.
        deadline = time.monotonic() + 15
        while len(calls) < len(targets) and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        assert len(calls) == len(targets), f"only {len(calls)} started"
        assert len(set(calls)) == len(targets), "a host was launched twice"

    def test_an_empty_batch_does_nothing(self, app, bulk, monkeypatch):
        opened = []
        monkeypatch.setattr(app, "_launch_ssh",
                            lambda *a, **k: opened.append(a))
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: opened.append("panel"))
        app.launch_ssh_batch([], "PuTTY", "putty.exe")
        assert opened == []

    def test_each_session_gets_its_own_arguments(self, app, bulk,
                                                 monkeypatch):
        """One client for the batch, but host, user and port are per
        entry -- the whole point of picking from a list."""
        seen = []
        monkeypatch.setattr(
            app, "_launch_ssh",
            lambda path, name, host, user, port, title:
                seen.append((host, user, port)))
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)
        _servers(app, [
            _entry(id="a", title="a", url="ssh://a.example.com:2200",
                   username="alice"),
            _entry(id="b", title="b", url="10.0.0.9", username="bob"),
        ])
        targets = bulk.collect_targets(app)
        app.launch_ssh_batch(targets, "PuTTY", "putty.exe")
        deadline = time.monotonic() + 15
        while len(seen) < 2 and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        assert ("a.example.com", "alice", 2200) in seen
        assert ("10.0.0.9", "bob", 22) in seen


class TestABatchThatOutlivesItsVault:
    """The chain runs for seconds. Anything can happen in them."""

    def test_locking_stops_the_rest_of_the_batch(self, app, bulk,
                                                 monkeypatch):
        """Otherwise queued callbacks keep opening sessions for a vault
        that is no longer unlocked."""
        calls = []
        monkeypatch.setattr(app, "_launch_ssh",
                            lambda *a, **k: calls.append(a[2]))
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)
        _servers(app, [_entry(id=str(i), title=f"s{i}",
                              url=f"10.0.0.{i}") for i in range(6)])
        app.launch_ssh_batch(bulk.collect_targets(app), "PuTTY", "p.exe")
        assert len(calls) == 1

        app._auto_lock()
        app.root.update()
        after_lock = len(calls)

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        assert len(calls) == after_lock,             "sessions kept opening after the vault locked"
        assert app._batch_timer is None

    def test_a_new_batch_replaces_the_one_still_running(self, app, bulk,
                                                        monkeypatch):
        """Two batches chaining at once would interleave their launches
        and neither would finish on the stagger it was given."""
        monkeypatch.setattr(app, "_launch_ssh", lambda *a, **k: None)
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)
        _servers(app, [_entry(id=str(i), title=f"s{i}",
                              url=f"10.0.0.{i}") for i in range(6)])
        targets = bulk.collect_targets(app)

        app.launch_ssh_batch(targets, "PuTTY", "p.exe")
        first = app._batch_timer
        app.launch_ssh_batch(targets, "PuTTY", "p.exe")
        assert app._batch_timer != first, "the first chain was left running"


class TestTheClipboard:
    def test_nothing_is_staged_by_the_batch_itself(self, app, bulk,
                                                   monkeypatch):
        """One clipboard cannot hold ten passwords. Staging one of them
        would put an arbitrary secret there and leave the user guessing
        which; the panel copies on request instead."""
        monkeypatch.setattr(app, "_launch_ssh", lambda *a, **k: None)
        monkeypatch.setattr(bulk, "show_password_panel",
                            lambda *a, **k: None)
        staged = []
        monkeypatch.setattr(app, "_stage_password_for_paste",
                            lambda *a, **k: staged.append(a))

        _servers(app, [_entry(id=str(i), title=f"s{i}",
                              url=f"10.0.0.{i}") for i in range(3)])
        app.launch_ssh_batch(bulk.collect_targets(app), "PuTTY", "p.exe")
        assert staged == [], "a password was copied without being asked for"

    def test_the_panel_copies_one_password_on_request(self, app, bulk,
                                                      monkeypatch):
        import main as main_module

        copied = []
        monkeypatch.setattr(main_module.pyperclip, "copy", copied.append)
        _servers(app, [_entry(password="hunter2")])
        panel = bulk.show_password_panel(app, bulk.collect_targets(app))
        app.root.update()
        try:
            buttons = _buttons(panel, "Copy")
            assert buttons, "the panel has no copy button"
            buttons[0].invoke()
            app.root.update()
            assert copied == ["hunter2"]
            assert app._clipboard_timer is not None, \
                "the password was copied but never scheduled to be cleared"
        finally:
            panel.destroy()
            app.root.update()


class TestTheLock:
    def test_the_password_panel_does_not_survive_a_lock(self, app, bulk):
        """It reaches every password in the batch. Leaving it up after an
        auto-lock would hand them to whoever walked past."""
        _servers(app, [_entry()])
        panel = bulk.show_password_panel(app, bulk.collect_targets(app))
        app.root.update()
        assert panel.winfo_exists()

        app._auto_lock()
        app.root.update()
        assert not panel.winfo_exists(), \
            "the panel outlived the vault it belongs to"
        assert app._session_panel is None


def _buttons(widget, text, out=None):
    import customtkinter as ctk

    out = [] if out is None else out
    if isinstance(widget, ctk.CTkButton) and text in str(widget.cget("text")):
        out.append(widget)
    for child in widget.winfo_children():
        _buttons(child, text, out)
    return out


class TestTheDialog:
    def test_it_opens_and_lists_the_servers(self, app, bulk):
        _servers(app, [_entry(id="a", title="web01", url="10.0.0.5"),
                       _entry(id="b", title="db01", url="10.0.0.6")])
        bulk.show(app)
        app.root.update()
        dlg = app._grab_stack[-1]
        try:
            text = _all_text(dlg)
            assert "web01" in text and "db01" in text
            assert "root@10.0.0.5" in text
        finally:
            dlg.destroy()
            app.root.update()

    def test_it_says_so_when_there_are_no_servers(self, app, bulk):
        _servers(app, [_entry(url="https://mail.example.com/in",
                              category="General")])
        bulk.show(app)
        app.root.update()
        dlg = app._grab_stack[-1]
        try:
            assert "No entries look like a server" in _all_text(dlg) or \
                "لا يوجد" in _all_text(dlg)
        finally:
            dlg.destroy()
            app.root.update()


def _all_text(widget, out=None):
    import customtkinter as ctk

    out = [] if out is None else out
    if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton, tk.Label)):
        try:
            out.append(str(widget.cget("text")))
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        _all_text(child, out)
    return " | ".join(out)
