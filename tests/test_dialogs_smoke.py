"""Every dialog opens, renders, and closes — in both themes.

MVP.md listed this as the missing gate: the floating widget, Mini Vault and
Security Dashboard were only ever checked with throwaway scripts. A dialog
that raises while building leaves a half-drawn window and, in a few cases,
an unreleased grab, so "it opened" is worth asserting on every change.

These are smoke tests, not appearance tests. They catch a broken build, a
missing theme token, and a grab that is never handed back — not a layout
that looks wrong.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display

THEMES = ["Light", "Dark"]


def _toplevels(app) -> list:
    return [w for w in app.root.winfo_children()
            if isinstance(w, tk.Toplevel)]


def _open(app, opener, *args):
    """Run *opener*, return the dialog it created, and drain Tk's queue.

    A full `update()` rather than `update_idletasks()`: the latter runs only
    idle callbacks, so the window is never mapped and a generated event has
    nowhere to land.
    """
    before = set(_toplevels(app))
    opener(app, *args)
    app.root.update()
    created = [w for w in _toplevels(app) if w not in before]
    assert created, "the dialog did not create a window"
    dlg = created[-1]
    assert dlg.winfo_viewable(), "the dialog was created but never mapped"
    return dlg


def _close(app, dlg):
    dlg.destroy()
    app.root.update()


# Openers that need nothing but the app itself.
SIMPLE_DIALOGS = {
    "about": lambda app: _import("about").show(app),
    "backup_export": lambda app: _import("backup").show_export(app),
    "backup_restore": lambda app: _import("backup").show_restore(app),
    "backup_restore_at_login":
        lambda app: _import("backup").show_restore_at_login(app),
    "change_password": lambda app: _import("change_password").show(app),
    "data_export": lambda app: _import("data_io").show_export(app),
    "data_import": lambda app: _import("data_io").show_import(app),
    "security_dashboard":
        lambda app: _import("security_dashboard").show(app),
    "trash": lambda app: _import("trash").show(app),
    "settings": lambda app: app.show_settings_dialog(),
    "add_category": lambda app: app.show_add_cat_dialog(),
    "new_entry": lambda app: app.show_entry_dialog(),
    "quit_confirm": lambda app: app.confirm_quit(),
    "alert": lambda app: app._alert("Title", "Message"),
}


def _import(name):
    import importlib
    return importlib.import_module(f"password_vault.ui.dialogs.{name}")


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("name", sorted(SIMPLE_DIALOGS))
def test_dialog_opens_in_both_themes(app, name, theme):
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    app.root.update_idletasks()
    dlg = _open(app, lambda a: SIMPLE_DIALOGS[name](a))
    assert dlg.winfo_exists()
    _close(app, dlg)


@pytest.mark.parametrize("name", sorted(SIMPLE_DIALOGS))
def test_dialog_opens_in_arabic(app, name, arabic):
    """Every dialog builds under a right-to-left layout.

    The direction helpers are read when a widget is created, so a call site
    that still passes a literal "w" or "left" does not fail here — but one
    that mirrors a value Tk will not accept does, and so does any string
    that goes missing from the catalog lookup.
    """
    dlg = _open(app, lambda a: SIMPLE_DIALOGS[name](a))
    assert dlg.winfo_exists()
    _close(app, dlg)


def test_arabic_actually_translates(app, arabic):
    """The catalog is wired up, not merely present."""
    from password_vault.i18n import t
    assert t("Settings") == "الإعدادات"
    assert t("Cancel") == "إلغاء"
    # A string with no entry falls back to English rather than to a key.
    assert t("__not in the catalog__") == "__not in the catalog__"


def test_arabic_mirrors_the_layout(app, arabic):
    from password_vault import i18n
    assert i18n.is_rtl()
    assert i18n.anchor_start() == "e"
    assert i18n.side_start() == "right"
    assert i18n.justify_start() == "right"
    assert i18n.pad(8, 0) == (0, 8)


def test_placeholders_survive_translation(app, arabic):
    from password_vault.i18n import t
    out = t("Open {url}", url="https://example.com")
    assert "https://example.com" in out
    out = t("🗑️  Recycle Bin ({count})", count=3)
    assert "3" in out


def test_every_catalog_entry_has_matching_placeholders():
    """A translation may reorder placeholders but not invent or drop them.

    A mismatch here would raise at runtime inside whichever dialog uses the
    string, which is exactly the class of bug a translated build hides
    until someone switches language.
    """
    import re
    from password_vault.i18n import ARABIC

    field = re.compile(r"\{(\w+)\}")
    bad = []
    for source, translated in ARABIC.items():
        if set(field.findall(source)) != set(field.findall(translated)):
            bad.append(source)
    assert not bad, f"placeholder mismatch in: {bad}"


@pytest.mark.parametrize("theme", THEMES)
def test_entry_dialog_opens_for_an_existing_entry(app, theme):
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    dlg = _open(app, lambda a: a.show_entry_dialog(a.data["entries"][0]))
    _close(app, dlg)


@pytest.mark.parametrize("theme", THEMES)
def test_delete_confirmations_open(app, theme):
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    dlg = _open(app, lambda a: a.confirm_delete(a.data["entries"][0]))
    _close(app, dlg)
    dlg = _open(app, lambda a: a.confirm_delete_category("Work"))
    _close(app, dlg)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("kind", ["ssh", "rdp"])
def test_remote_session_dialogs_open(app, theme, kind):
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    entry = app.data["entries"][1]
    dlg = _open(app, lambda a: a._show_remote_session_dialog(
        entry, kind=kind))
    _close(app, dlg)


@pytest.mark.parametrize("theme", THEMES)
def test_generator_opens_over_the_entry_dialog(app, theme):
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    entry_dlg = _open(app, lambda a: a.show_entry_dialog())
    # The generator writes into a field, so it needs one to target.
    target = _first_entry_widget(entry_dlg)
    assert target is not None, "no entry field found in the entry dialog"
    gen = _open(app, lambda a: a._show_generator(target))
    _close(app, gen)
    _close(app, entry_dlg)


def _first_entry_widget(widget):
    import customtkinter as ctk
    if isinstance(widget, ctk.CTkEntry):
        return widget
    for child in widget.winfo_children():
        found = _first_entry_widget(child)
        if found is not None:
            return found
    return None


def test_mini_vault_and_floating_widget_build(app):
    from password_vault.ui.floating import FloatingWidget
    from password_vault.ui.mini_vault import MiniVault

    mini = MiniVault(app)
    app.root.update_idletasks()
    assert mini.winfo_exists()
    mini.destroy()

    widget = FloatingWidget(app)
    app.root.update_idletasks()
    assert widget.winfo_exists()
    widget.destroy()


def test_nested_dialog_hands_the_grab_back(app):
    """Closing a nested dialog must leave the one underneath modal.

    Tk keeps one grab per display, so a child taking it used to leave the
    parent non-modal for the rest of its life.
    """
    outer = _open(app, lambda a: a.show_entry_dialog())
    target = _first_entry_widget(outer)
    inner = _open(app, lambda a: a._show_generator(target))
    assert app._grab_stack[-1] is inner
    _close(app, inner)
    assert app._grab_stack[-1] is outer
    assert outer.grab_current() == outer
    _close(app, outer)
    assert app._grab_stack == []


@pytest.mark.parametrize("theme", THEMES)
def test_confirmations_route_through_the_shared_grab_stack(app, theme):
    """Every confirm goes through `app._confirm`, so it must be tracked.

    The Recycle Bin used to build its own toplevels and take the grab
    through a second mechanism, which left them out of `_grab_stack`
    entirely.
    """
    import customtkinter as ctk
    ctk.set_appearance_mode(theme)
    bin_dlg = _open(app, lambda a: _import("trash").show(a))
    depth = len(app._grab_stack)

    empty = _open(app, lambda a: _find_button(bin_dlg, "Empty Trash")())
    assert len(app._grab_stack) == depth + 1
    assert app._grab_stack[-1] is empty
    _close(app, empty)
    assert app._grab_stack[-1] is bin_dlg
    _close(app, bin_dlg)


@pytest.mark.parametrize("opener,label", [
    (lambda a: a.confirm_delete(a.data["entries"][0]), "Cancel"),
    (lambda a: a.confirm_delete_category("Work"), "Cancel"),
    (lambda a: a.confirm_quit(), "Cancel"),
])
def test_enter_cancels_a_destructive_confirmation(app, opener, label):
    """Enter must never be the key that confirms a destructive action."""
    dlg = _open(app, opener)
    entries_before = len(app.data["entries"])
    cats_before = len(app.data["categories"])
    # A queued key event is routed to whatever holds focus, which under a
    # shared root is not reliably this dialog. `when="now"` delivers it
    # straight to the widget the binding is on.
    dlg.event_generate("<Return>", when="now")
    app.root.update()
    assert not dlg.winfo_exists(), "Enter should dismiss the dialog"
    assert len(app.data["entries"]) == entries_before
    assert len(app.data["categories"]) == cats_before


def _find_button(widget, text):
    """Return the command of the first button whose label contains *text*."""
    import customtkinter as ctk
    if isinstance(widget, ctk.CTkButton) and text in widget.cget("text"):
        return widget.cget("command")
    for child in widget.winfo_children():
        found = _find_button(child, text)
        if found is not None:
            return found
    return None


def test_auto_lock_closes_every_dialog(app):
    """No plaintext may be left on screen behind the login window."""
    _open(app, lambda a: a.show_entry_dialog(a.data["entries"][0]))
    _open(app, lambda a: _import("trash").show(a))
    assert len(_toplevels(app)) >= 2
    app._auto_lock()
    app.root.update_idletasks()
    assert _toplevels(app) == []
    assert app.key is None
    assert app.data is None
