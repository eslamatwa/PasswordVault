"""Encrypted backup — export to a portable file & restore from one.

The backup file is independent of the live vault: it carries its own
salt and KDF parameters, encrypted with a separate backup password
that the user chooses. This lets the user recover their entries even
if they forget their master password — provided they kept the backup
file and remember its password.
"""

from __future__ import annotations

import logging
import os

import customtkinter as ctk
from tkinter import filedialog as tkfiledialog

from ...crypto import (
    derive_key, export_encrypted_backup, get_or_create_salt,
    import_encrypted_backup, rotate_salt, save_data,
)
from ...security import password_strength
from ...theme import (
    ACCENT, ACCENT_HOVER, BG, BG_TERT, CARD_HOVER,
    GREEN, GREEN_HOVER, ORANGE, ORANGE_HOVER, RED,
    TEXT_PRI, TEXT_QUAT, TEXT_SEC,
)
from ..widgets import ios_field, ios_group, tip

log = logging.getLogger("PasswordVault")


# ─── Export Encrypted Backup ─────────────────────────────────
def show_export(app) -> None:
    """Prompt the user for a backup password, then write a portable
    encrypted backup file."""
    dlg = app._make_dialog("Encrypted Backup", 420, 460)

    ctk.CTkLabel(dlg, text="🛟  Encrypted Backup",
                  font=ctk.CTkFont(family="Segoe UI", size=16,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(14, 4))

    info = ctk.CTkFrame(dlg, fg_color="#22283a", corner_radius=10)
    info.pack(fill="x", padx=20, pady=(8, 12))
    ctk.CTkLabel(
        info,
        text=("Use this if you ever forget your master password.\n"
              "The backup is encrypted with a SEPARATE password\n"
              "you choose below. Keep it somewhere safe."),
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=ACCENT, justify="center").pack(padx=12, pady=8)

    frm = ctk.CTkFrame(dlg, fg_color="transparent")
    frm.pack(fill="both", expand=True, padx=18, pady=(0, 4))

    g1 = ios_group(frm, "Backup Password")
    new_e = ios_field(g1, "Password", idx=0, show="●")
    conf_e = ios_field(g1, "Confirm", idx=1, show="●")

    sf = ctk.CTkFrame(frm, fg_color="transparent")
    sf.pack(fill="x", padx=14, pady=(2, 0))
    sb = ctk.CTkProgressBar(sf, height=4, corner_radius=2,
                              fg_color=BG_TERT,
                              progress_color=TEXT_QUAT)
    sb.pack(side="left", fill="x", expand=True)
    sb.set(0)
    sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                        text_color=TEXT_QUAT)
    sl.pack(side="left", padx=(6, 0))

    def upd(_e=None):
        s, l, c = password_strength(new_e.get())
        sb.set(s / 4)
        sb.configure(progress_color=c)
        sl.configure(text=l, text_color=c)

    new_e.bind("<KeyRelease>", upd)

    err = ctk.CTkLabel(frm, text="", text_color=RED,
                        font=ctk.CTkFont(size=11))
    err.pack(pady=(6, 4))

    def do_export():
        bp = new_e.get()
        cp = conf_e.get()
        if not bp:
            err.configure(text="⚠️ Enter a backup password")
            return
        if bp != cp:
            err.configure(text="⚠️ Passwords don't match")
            return
        if len(bp) < 8:
            err.configure(text="⚠️ Use at least 8 characters")
            return
        path = tkfiledialog.asksaveasfilename(
            parent=dlg, defaultextension=".pvbak",
            filetypes=[("Password Vault Backup", "*.pvbak"),
                        ("All files", "*.*")],
            initialfile="vault-backup.pvbak")
        if not path:
            return
        try:
            export_encrypted_backup(app.data, bp, path)
        except (OSError, ValueError) as exc:
            err.configure(text=f"⚠️ {exc}")
            return
        log.info("Encrypted backup exported by user.")
        # Confirmation message inside the dialog so we can keep
        # everything self-contained.
        for w in dlg.winfo_children():
            w.destroy()
        ctk.CTkLabel(dlg, text="✅", font=ctk.CTkFont(size=48)).pack(
            pady=(40, 8))
        ctk.CTkLabel(dlg, text="Backup created!",
                      font=ctk.CTkFont(family="Segoe UI", size=16,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 4))
        ctk.CTkLabel(
            dlg, text=f"Saved to:\n{path}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_SEC, wraplength=380,
            justify="center").pack(padx=20, pady=(0, 12))
        ctk.CTkLabel(
            dlg,
            text="⚠️  Keep this file AND its password safe.\n"
                 "Without both, the backup cannot be opened.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=ORANGE, justify="center").pack(pady=(0, 16))
        ctk.CTkButton(
            dlg, text="Close", height=36, width=140,
            font=ctk.CTkFont(size=13), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=10,
            command=dlg.destroy).pack()

    save_btn = ctk.CTkButton(
        frm, text="🛟  Create Backup", height=38,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
        corner_radius=10, command=do_export)
    save_btn.pack(fill="x", padx=14, pady=(0, 6))
    tip(save_btn, "Encrypt the vault and save it to a backup file")
    dlg.bind("<Return>", lambda _e: do_export())
    new_e.focus()


# ─── Restore From Backup ─────────────────────────────────────
def show_restore(app) -> None:
    """Restore vault contents from an encrypted backup. The current
    master password is preserved (if any); the restored entries
    overwrite the current vault.

    NOTE: Caller must pass an `app` that is already unlocked.
    For the unlocked-restore flow only.
    """
    _show_restore_dialog(app, on_restore=_restore_into_unlocked_vault)


def show_restore_at_login(login_app) -> None:
    """Restore from a backup at login time (no current vault required).

    The user provides the backup password to decrypt the file, and a
    new master password to re-encrypt the imported data on disk.
    """
    _show_restore_dialog(login_app, on_restore=_restore_to_new_vault,
                          at_login=True)


# ── Internal: shared restore dialog UI ──
def _show_restore_dialog(app, *, on_restore, at_login: bool = False) -> None:
    title = "Restore From Backup"
    dlg = app._make_dialog(title, 420,
                            520 if at_login else 420)

    ctk.CTkLabel(dlg, text="🛟  Restore From Backup",
                  font=ctk.CTkFont(family="Segoe UI", size=16,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(14, 4))

    if at_login:
        warn = ctk.CTkFrame(dlg, fg_color="#3a2a20", corner_radius=10)
        warn.pack(fill="x", padx=20, pady=(8, 8))
        ctk.CTkLabel(
            warn,
            text=("Restoring will create a new vault from this backup.\n"
                  "You'll set a new master password below."),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=ORANGE, justify="center").pack(padx=12, pady=8)
    else:
        warn = ctk.CTkFrame(dlg, fg_color="#3a2a20", corner_radius=10)
        warn.pack(fill="x", padx=20, pady=(8, 8))
        ctk.CTkLabel(
            warn,
            text=("⚠️  This will REPLACE all entries currently in\n"
                  "your vault with the contents of the backup."),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=ORANGE, justify="center").pack(padx=12, pady=8)

    frm = ctk.CTkFrame(dlg, fg_color="transparent")
    frm.pack(fill="both", expand=True, padx=18, pady=(0, 6))

    # File picker
    file_state = {"path": ""}
    file_lbl = ctk.CTkLabel(frm, text="No file selected",
                              font=ctk.CTkFont(size=11),
                              text_color=TEXT_SEC, anchor="w")
    file_lbl.pack(fill="x", pady=(2, 4))

    def browse():
        path = tkfiledialog.askopenfilename(
            parent=dlg,
            filetypes=[("Password Vault Backup", "*.pvbak"),
                        ("All files", "*.*")])
        if path:
            file_state["path"] = path
            file_lbl.configure(text=os.path.basename(path),
                                 text_color=TEXT_PRI)

    ctk.CTkButton(
        frm, text="📂  Browse Backup File...", height=34,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=8,
        command=browse).pack(fill="x", pady=(0, 8))

    g1 = ios_group(frm, "Backup Password")
    bp_e = ios_field(g1, "Password", idx=0, show="●")

    # New master password fields (login flow only)
    new_master_e = None
    new_master_conf_e = None
    if at_login:
        g2 = ios_group(frm, "New Master Password")
        new_master_e = ios_field(g2, "Password", idx=0, show="●")
        new_master_conf_e = ios_field(g2, "Confirm", idx=1, show="●")

    err = ctk.CTkLabel(frm, text="", text_color=RED,
                        font=ctk.CTkFont(size=11))
    err.pack(pady=(4, 4))

    def do_restore():
        path = file_state["path"]
        if not path:
            err.configure(text="⚠️ Pick a backup file first")
            return
        if not os.path.exists(path):
            err.configure(text="⚠️ File not found")
            return
        bp = bp_e.get()
        if not bp:
            err.configure(text="⚠️ Enter the backup password")
            return
        try:
            data = import_encrypted_backup(path, bp)
        except (OSError, ValueError) as exc:
            err.configure(text=f"⚠️ {exc}")
            return
        if at_login:
            new_master = new_master_e.get() if new_master_e else ""
            new_conf = (new_master_conf_e.get()
                        if new_master_conf_e else "")
            if not new_master:
                err.configure(text="⚠️ Set a new master password")
                return
            if new_master != new_conf:
                err.configure(text="⚠️ Master passwords don't match")
                return
            ve = (app._validate_master_password(new_master)
                  if hasattr(app, "_validate_master_password")
                  else _basic_master_check(new_master))
            if ve:
                err.configure(text=ve)
                return
        try:
            on_restore(app, data, dlg, new_master if at_login else None)
        except (OSError, ValueError) as exc:
            err.configure(text=f"⚠️ Restore failed: {exc}")
            return

    btn = ctk.CTkButton(
        frm, text="🛟  Restore", height=38,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color=ORANGE, hover_color=ORANGE_HOVER,
        corner_radius=10, command=do_restore)
    btn.pack(fill="x", padx=14, pady=(2, 4))
    tip(btn, "Decrypt the backup and load it into the vault")
    dlg.bind("<Return>", lambda _e: do_restore())


def _basic_master_check(pw: str) -> str | None:
    if len(pw) < 12:
        return "⚠️ Master password must be 12+ chars"
    if not any(c.isupper() for c in pw):
        return "⚠️ Need an uppercase letter"
    if not any(c.islower() for c in pw):
        return "⚠️ Need a lowercase letter"
    if not any(c.isdigit() for c in pw):
        return "⚠️ Need a digit"
    return None


def _restore_into_unlocked_vault(app, data: dict, dlg, _new_master) -> None:
    """Replace current entries with backup contents, re-encrypt with
    the existing master key. Leaves the master password unchanged."""
    app.data = data
    save_data(app.data, app.key)
    log.info("Vault restored from backup (unlocked).")
    if hasattr(app, "refresh_categories"):
        app.refresh_categories()
    if hasattr(app, "refresh_entries"):
        app.refresh_entries()
    dlg.destroy()


def _restore_to_new_vault(app, data: dict, dlg, new_master: str) -> None:
    """Restore at login: rotate salt, derive a new master key, save the
    backup data encrypted with that key, then unlock the app."""
    new_salt = os.urandom(32)
    new_key = derive_key(new_master, new_salt)
    # Save with new key first; only then commit the new salt.
    app.key = new_key
    app.data = data
    save_data(app.data, app.key)
    rotate_salt(new_salt)
    log.info("Vault restored from backup at login (new master set).")
    dlg.destroy()
    # Hand off to the live app login flow.
    if hasattr(app, "_finish_unlock_after_restore"):
        app._finish_unlock_after_restore()
