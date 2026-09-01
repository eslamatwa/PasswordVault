"""The Advanced section of the entry dialog.

It exists because the dialog had reached ten fields across five groups
and the SSH key work would have added five more — pushing the four
fields nearly every entry uses into a minority of the form.

Two rules it has to keep. Nothing set inside may be invisible: a
collapsed section silently in force is worse than a long form, so the
header names what is in there. And it must not argue with the user —
opening itself because they chose a server category is helpful once, and
irritating if it happens again after they close it.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _entry(**over):
    base = {"id": "e", "title": "thing", "username": "u", "password": "p",
            "url": "", "category": "General", "notes": "", "color": "default",
            "pinned": False, "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-01T00:00:00"}
    base.update(over)
    return base


def _widgets(root, out=None):
    out = [] if out is None else out
    out.append(root)
    for child in root.winfo_children():
        _widgets(child, out)
    return out


def _advanced(dlg):
    """The Advanced group, found by the API collapsible_group adds."""
    for widget in _widgets(dlg):
        if hasattr(widget, "is_open") and hasattr(widget, "open_it"):
            return widget
    raise AssertionError("no collapsible group in the entry dialog")


def _header_text(dlg):
    import customtkinter as ctk

    return " ".join(str(getattr(w, "_text", "")) for w in _widgets(dlg)
                    if isinstance(w, ctk.CTkLabel))


@pytest.fixture
def dialog(app):
    opened = []

    def show(entry=None):
        app.show_entry_dialog(entry)
        app.root.update()
        dlg = app._grab_stack[-1]
        opened.append(dlg)
        return dlg

    yield app, show
    for dlg in opened:
        try:
            if dlg.winfo_exists():
                dlg.destroy()
        except tk.TclError:
            pass
    app.root.update()


class TestItStartsClosed:
    def test_a_plain_new_entry_hides_the_advanced_fields(self, dialog):
        app, show = dialog
        app.data["entries"] = []
        assert not _advanced(show()).is_open()

    def test_an_ordinary_entry_hides_them_too(self, dialog):
        app, show = dialog
        entry = _entry(category="General")
        app.data["entries"] = [entry]
        assert not _advanced(show(entry)).is_open()


class TestItOpensWhenThereIsSomethingToSee:
    """Hidden is fine. Silently in force is not."""

    @pytest.mark.parametrize("field,value", [
        ("match_patterns", "*.corp.local"),
        ("general_account", True),
        ("ssh_key_source", "stored"),
    ])
    def test_an_entry_with_advanced_settings_opens(self, dialog, field,
                                                   value):
        app, show = dialog
        entry = _entry(**{field: value})
        app.data["entries"] = [entry]
        assert _advanced(show(entry)).is_open(), \
            f"{field} was set and the section stayed shut"

    def test_a_server_entry_opens(self, dialog):
        """Filed as a server means the key fields are worth seeing
        without hunting for them."""
        app, show = dialog
        entry = _entry(category="Server", url="10.0.0.5")
        app.data["entries"] = [entry]
        assert _advanced(show(entry)).is_open()

    def test_the_closed_header_says_what_is_set(self, dialog):
        """Otherwise a pattern quietly matching windows is invisible."""
        app, show = dialog
        entry = _entry(match_patterns="*.corp.local")
        app.data["entries"] = [entry]
        dlg = show(entry)
        group = _advanced(dlg)
        group.close_it()
        app.root.update()
        assert not group.is_open()
        assert "auto-type" in _header_text(dlg).lower(),             "a pattern is quietly matching windows and nothing says so"


class TestTheServerCategoryNudge:
    def test_choosing_a_server_category_opens_it(self, dialog):
        """The moment someone is thinking about a machine is the moment
        the key fields should turn up."""
        app, show = dialog
        app.data["entries"] = []
        dlg = show()
        group = _advanced(dlg)
        assert not group.is_open()

        # Drive the combo's own callback, which is what a pick does.
        import customtkinter as ctk

        combos = [w for w in _widgets(dlg)
                  if isinstance(w, ctk.CTkComboBox)]
        assert combos, "no category combo in the dialog"
        combos[0].set("Server")
        combos[0]._command("Server")
        app.root.update()
        assert group.is_open(), "picking a server category did nothing"



    def test_it_does_not_reopen_after_you_close_it(self, dialog):
        """Helpful once. Arguing with the user if it happens again."""
        import customtkinter as ctk

        app, show = dialog
        app.data["entries"] = []
        dlg = show()
        group = _advanced(dlg)
        combos = [w for w in _widgets(dlg) if isinstance(w, ctk.CTkComboBox)]
        combos[0]._command("Server")
        app.root.update()
        assert group.is_open()

        group.close_it()
        app.root.update()
        combos[0]._command("Database")
        app.root.update()
        assert not group.is_open(),             "reopened a section the user had deliberately closed"

    @pytest.mark.parametrize("category,expected", [
        ("Server", True), ("VPN", True), ("Database", True),
        ("SSH", True), ("RDP", True),
        ("General", False), ("Social", False), ("", False),
        ("  server  ", True), ("SERVER", True),
    ])
    def test_which_categories_count_as_machines(self, app, category,
                                                expected):
        """The same set the right-click menu uses, so "this is a server"
        means one thing across the app."""
        assert app._server_category(category) is expected


class TestWhatItHolds:
    def test_the_ssh_key_and_auto_type_fields_are_inside(self, dialog):
        app, show = dialog
        entry = _entry(category="Server")
        app.data["entries"] = [entry]
        dlg = show(entry)
        text = _header_text(dlg)
        for label in ("Window patterns", "Typing order", "SSH key"):
            assert label in text, f"{label} is not in the dialog"

    def test_the_common_fields_stay_out_of_it(self, dialog):
        """The whole point: what nearly every entry needs is not behind
        a disclosure."""
        app, show = dialog
        app.data["entries"] = []
        dlg = show()
        group = _advanced(dlg)
        inside = " ".join(str(getattr(w, "_text", ""))
                          for w in _widgets(group))
        for label in ("Title", "Username", "Password"):
            assert label not in inside, f"{label} was hidden away"
