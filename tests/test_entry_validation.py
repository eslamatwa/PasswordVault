"""The entry dialog's own error messages.

These existed and had never been exercised. The dialog's save handler
bound a local named `t` to the title, which shadows the translation
function for the whole function — so every validation message in it was
a call on a string, and pressing Save with an empty title raised
`TypeError: 'str' object is not callable` instead of saying what was
wrong. Two of the three call sites predated the auto-type work; the
third was added by it, the same way.

The lesson these hold: a guard that has never been triggered in a test
is not a guard, it is a line of code that looks like one.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _widgets(root, out=None):
    out = [] if out is None else out
    out.append(root)
    for child in root.winfo_children():
        _widgets(child, out)
    return out


def _entry_boxes(dlg):
    import customtkinter as ctk

    return [w for w in _widgets(dlg) if isinstance(w, ctk.CTkEntry)]


def _save_button(dlg):
    import customtkinter as ctk

    for widget in _widgets(dlg):
        if isinstance(widget, ctk.CTkButton) and "Save" in str(
                getattr(widget, "_text", "")):
            return widget
    raise AssertionError("no Save button in the entry dialog")


def _error_text(dlg):
    import customtkinter as ctk

    texts = [str(getattr(w, "_text", "")) for w in _widgets(dlg)
             if isinstance(w, ctk.CTkLabel)]
    return " | ".join(x for x in texts if x)


@pytest.fixture
def dialog(app):
    app.data["entries"] = []
    app.show_entry_dialog()
    app.root.update()
    dlg = app._grab_stack[-1]
    yield app, dlg
    try:
        if dlg.winfo_exists():
            dlg.destroy()
    except tk.TclError:
        pass
    app.root.update()


class TestItReportsInsteadOfCrashing:
    def test_an_empty_title_shows_the_error(self, dialog):
        app, dlg = dialog
        _save_button(dlg).invoke()
        app.root.update()
        assert dlg.winfo_exists(), "the dialog closed on an invalid save"
        assert "Title" in _error_text(dlg) or "عنوان" in _error_text(dlg)

    def test_an_empty_password_shows_the_error(self, dialog):
        app, dlg = dialog
        boxes = _entry_boxes(dlg)
        boxes[0].insert(0, "Something")
        _save_button(dlg).invoke()
        app.root.update()
        assert dlg.winfo_exists()
        text = _error_text(dlg)
        assert "Password" in text or "المرور" in text or "السر" in text

    def test_a_broken_typing_order_shows_the_error(self, dialog):
        """Refused here rather than when someone is standing in front of
        a login box waiting for it."""
        app, dlg = dialog
        boxes = _entry_boxes(dlg)
        boxes[0].insert(0, "Something")
        sequence = [b for b in boxes
                    if "{USERNAME}" in str(b.get())]
        assert sequence, "no typing-order field in the dialog"
        sequence[0].delete(0, "end")
        sequence[0].insert(0, "{NOPE}")
        for box in boxes:
            if box is not sequence[0] and not box.get():
                box.insert(0, "x")
        _save_button(dlg).invoke()
        app.root.update()
        assert dlg.winfo_exists(), "saved a sequence that cannot be run"
        text = _error_text(dlg)
        assert "NOPE" in text or "Typing" in text or "الكتابة" in text

    def test_nothing_is_written_when_validation_fails(self, dialog):
        app, dlg = dialog
        _save_button(dlg).invoke()
        app.root.update()
        assert app.data["entries"] == [], "an invalid entry was saved"


class TestAValidEntrySaves:
    def test_it_closes_and_keeps_the_values(self, dialog):
        app, dlg = dialog
        boxes = _entry_boxes(dlg)
        boxes[0].insert(0, "My Thing")
        for box in boxes[1:]:
            if not box.get():
                box.insert(0, "filled")
        _save_button(dlg).invoke()
        app.root.update()
        assert app.data["entries"], "a valid entry was not saved"
        saved = app.data["entries"][0]
        assert saved["title"] == "My Thing", \
            "the title was lost — it shares a name with nothing now"
        assert saved["password"]
