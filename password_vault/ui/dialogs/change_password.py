"""Change Master Password dialog — re-encrypts vault with rotated salt."""

from __future__ import annotations

import hmac
import logging
import os

import customtkinter as ctk

from ...crypto import derive_key, get_or_create_salt, rotate_salt, save_data
from ...security import password_strength
from ...theme import (
    BG_TERT, ORANGE, ORANGE_HOVER, RED, TEXT_PRI, TEXT_QUAT,
)
from ..widgets import ios_field, ios_group, tip

log = logging.getLogger("PasswordVault")


def show(app) -> None:
    dlg = app._make_dialog("Change Master Password", 400, 380)

    ctk.CTkLabel(dlg, text="🔑", font=ctk.CTkFont(size=32)).pack(
        pady=(16, 2))
    ctk.CTkLabel(
        dlg, text="Change Master Password",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_PRI).pack(pady=(0, 10))

    frm = ctk.CTkFrame(dlg, fg_color="transparent")
    frm.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    g1 = ios_group(frm, "Current")
    old_e = ios_field(g1, "Password", idx=0, show="●")

    g2 = ios_group(frm, "New Password")
    new_e = ios_field(g2, "Password", idx=0, show="●")

    sf = ctk.CTkFrame(frm, fg_color="transparent")
    sf.pack(fill="x", padx=14, pady=(0, 4))
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

    g3 = ios_group(frm, "Confirm")
    conf_e = ios_field(g3, "Password", idx=0, show="●")

    err = ctk.CTkLabel(frm, text="", text_color=RED,
                        font=ctk.CTkFont(size=11))
    err.pack(pady=(2, 4))

    def save():
        op = old_e.get()
        np_ = new_e.get()
        cp = conf_e.get()
        if not op or not np_:
            err.configure(text="⚠️ Fill all fields")
            return
        salt = get_or_create_salt()
        if not hmac.compare_digest(derive_key(op, salt), app.key):
            err.configure(text="⚠️ Current password is wrong")
            return
        if np_ != cp:
            err.configure(text="⚠️ New passwords don't match")
            return
        ve = app._validate_master_password(np_)
        if ve:
            err.configure(text=ve)
            return
        # Rotate salt + re-derive key + re-encrypt vault. Atomic order:
        # 1) compute new key with new salt
        # 2) save vault encrypted with new key (atomic write to .tmp)
        # 3) only after save succeeds, persist new salt
        # If step 2 fails, salt is unchanged and old key still works.
        new_salt = os.urandom(32)
        new_key = derive_key(np_, new_salt)
        try:
            save_data(app.data, new_key)
        except (OSError, ValueError) as exc:
            log.error("Re-encrypt during password change failed: %s",
                      exc, exc_info=True)
            err.configure(text="⚠️ Could not save — try again")
            return
        rotate_salt(new_salt)
        app.key = new_key
        log.info("Master password changed; salt rotated.")
        dlg.destroy()

    save_btn = ctk.CTkButton(
        frm, text="Change Password", height=38,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color=ORANGE, hover_color=ORANGE_HOVER, corner_radius=10,
        command=save)
    save_btn.pack(fill="x", padx=14)
    tip(save_btn, "Save the new master password")
    dlg.bind("<Return>", lambda _e: save())
    old_e.focus()
