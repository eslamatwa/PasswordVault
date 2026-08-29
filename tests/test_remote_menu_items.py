"""SSH and RDP appear on every entry's menu, in both lists.

They used to be added only when the entry looked like a remote host, and
left out entirely otherwise. That reads as the feature being missing
rather than not applicable: nothing on screen says the actions exist, why
this entry cannot use them, or what to change. A vault whose entries all
happen to be ordinary logins shows no trace of SSH support at all.

They are shown greyed with the reason instead, which is how the same menu
already treats "Open URL in Browser" on an entry with no URL.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _entry(**over):
    base = {"id": "x", "title": "thing", "username": "u",
            "password": "p", "url": "", "category": "General",
            "notes": "", "color": "default", "pinned": False,
            "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-01T00:00:00"}
    base.update(over)
    return base


class _Recorder(tk.Menu):
    """A menu that remembers what was put on it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items: list[tuple[str, str]] = []

    def add_command(self, **kwargs):
        self.items.append((str(kwargs.get("label", "")),
                           str(kwargs.get("state", "normal"))))
        super().add_command(**kwargs)


def _items(app, entry):
    menu = _Recorder(app.root, tearoff=0)
    try:
        app._add_remote_items(menu, entry, entry.get("url", ""))
        return menu.items
    finally:
        menu.destroy()


def _find(items, word):
    return [(label, state) for label, state in items if word in label]


class TestTheyAreAlwaysThere:
    @pytest.mark.parametrize("entry", [
        _entry(),
        _entry(url="https://mail.example.com/login"),
        _entry(url="", category="General"),
        _entry(url="10.0.0.5", category="Server"),
    ])
    def test_both_actions_are_offered_whatever_the_entry(self, app, entry):
        items = _items(app, entry)
        assert _find(items, "SSH"), "no SSH item at all"
        assert _find(items, "RDP"), "no RDP item at all"


class TestWhenTheyWork:
    def test_a_server_entry_gets_them_enabled(self, app):
        items = _items(app, _entry(url="10.0.0.5", category="Server"))
        assert all(state == "normal" for _, state in items), items

    def test_an_ssh_url_gets_them_enabled(self, app):
        items = _items(app, _entry(url="ssh://box.example.com"))
        assert all(state == "normal" for _, state in items), items


class TestWhenTheyDoNot:
    def test_an_ordinary_entry_gets_them_greyed(self, app):
        """The entry in the report: no URL, an everyday category."""
        items = _items(app, _entry())
        assert items, "nothing was added"
        assert all(state == "disabled" for _, state in items), items

    def test_the_greyed_items_say_what_to_change(self, app):
        """A dead menu entry with no reason is barely better than a
        missing one."""
        items = _items(app, _entry())
        for label, _state in items:
            assert "host" in label.lower() or "IP" in label, \
                f"no reason given: {label!r}"

    def test_a_webmail_entry_is_still_not_a_server(self, app):
        """Greying them out is a presentation change. It must not quietly
        turn into offering SSH on every entry that has a URL."""
        items = _items(app, _entry(url="https://mail.example.com/login"))
        assert all(state == "disabled" for _, state in items), items


class TestBothMenusAgree:
    def test_the_mini_vault_uses_the_same_helper(self):
        """Two copies of this rule would drift; the Mini Vault menu had
        already been written out separately once."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent
        mini = (root / "password_vault" / "ui" / "mini_vault.py").read_text(
            encoding="utf-8")
        assert "_add_remote_items" in mini, \
            "the Mini Vault builds its own SSH/RDP items again"
        assert "_show_ssh_dialog(entry))" not in mini, \
            "the Mini Vault still has its own copy of the SSH item"

    def test_the_main_menu_shows_them_for_a_plain_entry(self, app):
        """End to end through the real menu builder, not the helper."""
        app.data["entries"] = [_entry()]
        app.refresh_entries()
        app.root.update()

        built = []
        real = tk.Menu

        class Spy(real):
            def add_command(self, **kwargs):
                built.append(str(kwargs.get("label", "")))
                super().add_command(**kwargs)

            def tk_popup(self, *args, **kwargs):
                pass

        tk.Menu = Spy
        try:
            event = type("E", (), {"x_root": 0, "y_root": 0})()
            app._show_context_menu(event, app.data["entries"][0])
        finally:
            tk.Menu = real
        assert any("SSH" in label for label in built), built
        assert any("RDP" in label for label in built), built
