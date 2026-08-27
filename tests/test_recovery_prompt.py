"""Telling the user, once, that a forgotten master password is final.

The encrypted backup is the only way back into a vault whose password has
been forgotten — no escrow, no reset link, no support address. That is the
point of the design, but it lived in a menu the user had no reason to open,
so a vault could be filled with passwords for months with nothing having
said there was no way back in.

The prompt fires once, at creation. These tests cover that it fires, that
it does not fire again, and that it says what it needs to say.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _toplevels(app):
    return [w for w in app.root.winfo_children()
            if isinstance(w, tk.Toplevel)]


def _labels(widget, out=None):
    import customtkinter as ctk
    out = [] if out is None else out
    if isinstance(widget, ctk.CTkLabel):
        out.append(widget)
    for child in widget.winfo_children():
        _labels(child, out)
    return out


def _text_of(dialog):
    return "\n".join(w.cget("text") for w in _labels(dialog)
                     if isinstance(w.cget("text"), str))


@pytest.fixture
def fresh_settings(app):
    """A settings dict that has never seen the prompt."""
    original = dict(app.settings)
    app.settings["backup_prompted"] = False
    yield app
    app.settings.clear()
    app.settings.update(original)


def _open_prompt(app):
    before = set(_toplevels(app))
    app._offer_first_backup()
    app.root.update()
    created = [w for w in _toplevels(app) if w not in before]
    return created[-1] if created else None


def test_the_prompt_appears_for_a_vault_that_has_never_had_one(
        fresh_settings):
    app = fresh_settings
    dlg = _open_prompt(app)
    assert dlg is not None, "the recovery warning never appeared"
    dlg.destroy()
    app.root.update()


def test_it_says_the_vault_cannot_be_recovered(fresh_settings):
    """The wording is the feature. A vague 'consider a backup' would not
    tell the user that this is irreversible."""
    app = fresh_settings
    dlg = _open_prompt(app)
    text = _text_of(dlg).lower()
    assert "recover" in text
    assert "forget" in text
    assert "no reset" in text
    dlg.destroy()
    app.root.update()


def test_it_offers_both_creating_a_backup_and_deferring(fresh_settings):
    import customtkinter as ctk

    app = fresh_settings
    dlg = _open_prompt(app)

    def buttons(widget, out=None):
        out = [] if out is None else out
        if isinstance(widget, ctk.CTkButton):
            out.append(widget.cget("text"))
        for child in widget.winfo_children():
            buttons(child, out)
        return out

    labels = " ".join(buttons(dlg))
    assert "Later" in labels
    assert "backup" in labels.lower()
    dlg.destroy()
    app.root.update()


def test_asking_marks_it_asked_so_it_never_nags(fresh_settings):
    app = fresh_settings
    dlg = _open_prompt(app)
    assert app.settings["backup_prompted"] is True
    dlg.destroy()
    app.root.update()

    # Even having dismissed it, a second call must not reopen it.
    assert _open_prompt(app) is None, "the warning came back"


def test_it_does_not_appear_when_already_prompted(app):
    app.settings["backup_prompted"] = True
    assert _open_prompt(app) is None


def test_creating_a_backup_records_when(app, tmp_path, monkeypatch):
    """`last_backup_at` is what lets the app answer "do I have one?"."""
    from password_vault.ui.dialogs import backup

    app.settings["last_backup_at"] = ""
    target = tmp_path / "vault.pvbak"
    monkeypatch.setattr(backup.tkfiledialog, "asksaveasfilename",
                        lambda **kw: str(target))

    before = set(_toplevels(app))
    backup.show_export(app)
    app.root.update()
    dlg = [w for w in _toplevels(app) if w not in before][-1]

    fields = []

    def collect(widget):
        import customtkinter as ctk
        if isinstance(widget, ctk.CTkEntry):
            fields.append(widget)
        for child in widget.winfo_children():
            collect(child)

    collect(dlg)
    assert len(fields) >= 2, "password and confirm fields not found"
    for field in fields[:2]:
        field.insert(0, "BackupPass123")

    # The export runs off the Tk thread and marshals back with after(),
    # which needs the main loop.
    import time
    deadline = time.time() + 30

    def poll():
        if app.settings.get("last_backup_at") or time.time() > deadline:
            app.root.quit()
        else:
            app.root.after(50, poll)

    _click_create(dlg)
    app.root.after(50, poll)
    app.root.mainloop()

    assert app.settings["last_backup_at"], "the backup time was not recorded"
    assert target.exists(), "no backup file was written"
    try:
        dlg.destroy()
    except tk.TclError:
        pass
    app.root.update()


def _click_create(dialog):
    import customtkinter as ctk

    def walk(widget):
        if isinstance(widget, ctk.CTkButton) and \
                "Create Backup" in str(widget.cget("text")):
            widget.invoke()
            return True
        return any(walk(child) for child in widget.winfo_children())

    assert walk(dialog), "the Create Backup button was not found"
