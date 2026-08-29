"""SSH and RDP are live on every entry's menu, in both lists.

Two wrong versions came before this one. First the items appeared only
when the entry looked like a remote host, which reads as the feature
being absent rather than inapplicable. Then they were shown greyed out
with a reason, which explained the situation but still refused the case
the feature is most useful for:

    one domain account opens dozens of machines

The entry holding those credentials has no host of its own and never
will, because the host is different every time. Requiring one on the
entry blocks exactly that workflow. The host belongs in the dialog, which
has a field for it and already refuses to connect without one.
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


class TestTheyAreAlwaysLive:
    @pytest.mark.parametrize("entry,why", [
        (_entry(url="10.0.0.5", category="Server"), "a plain server"),
        (_entry(url="ssh://box.example.com"), "an ssh url"),
        (_entry(), "a domain account with no host of its own"),
        (_entry(url="https://mail.example.com/login"), "a webmail login"),
    ])
    def test_nothing_is_greyed_out(self, app, entry, why):
        items = _items(app, entry)
        assert items, f"nothing added for {why}"
        assert all(state == "normal" for _, state in items), \
            f"{why} was refused: {items}"

    def test_the_domain_account_case_specifically(self, app):
        """The report this came from: an entry holding a domain login,
        no URL, an everyday category. It must be able to start a session
        and type the host into the dialog."""
        items = _items(
            app, _entry(title="domain admin", username=r"corp\eslam"))
        assert [state for _, state in items] == ["normal", "normal"]


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
