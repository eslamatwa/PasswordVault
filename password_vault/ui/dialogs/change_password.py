"""Change Master Password dialog — re-encrypts vault with rotated salt."""

from __future__ import annotations

import hmac
import logging
import os
import threading
import tkinter as tk

import customtkinter as ctk

from ...crypto import derive_key, get_or_create_salt, rotate_salt, save_data
from ...security import password_strength
from ...theme import (
    BG_TERT, ORANGE, ORANGE_HOVER, RED, TEXT_PRI, TEXT_QUAT, TEXT_SEC,
)
from ..widgets import ios_field, ios_group, tip

log = logging.getLogger("PasswordVault")

# Key derivation runs 480k PBKDF2 iterations; keep the strength meter cheap.
STRENGTH_DEBOUNCE_MS = 200


def show(app) -> None:
    dlg = app._make_dialog("Change Master Password", 400, 400)

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

    def upd():
        s, l, c = password_strength(new_e.get())
        sb.set(s / 4)
        sb.configure(progress_color=c)
        sl.configure(text=l, text_color=c)

    _str_timer: list = [None]

    def on_key(_e=None):
        if _str_timer[0]:
            try:
                dlg.after_cancel(_str_timer[0])
            except (tk.TclError, ValueError):
                pass
        _str_timer[0] = dlg.after(STRENGTH_DEBOUNCE_MS, upd)

    new_e.bind("<KeyRelease>", on_key)

    g3 = ios_group(frm, "Confirm")
    conf_e = ios_field(g3, "Password", idx=0, show="●")

    err = ctk.CTkLabel(frm, text="", text_color=RED,
                        font=ctk.CTkFont(size=11))
    err.pack(pady=(2, 0))

    status = ctk.CTkLabel(frm, text="", text_color=TEXT_SEC,
                            font=ctk.CTkFont(size=11))
    status.pack(pady=(0, 4))

    busy = {"on": False}

    def set_busy(on: bool):
        busy["on"] = on
        save_btn.configure(
            state="disabled" if on else "normal",
            text="⏳  Re-encrypting…" if on else "Change Password")

    def save():
        if busy["on"]:
            return
        op = old_e.get()
        np_ = new_e.get()
        cp = conf_e.get()
        if not op or not np_ or not cp:
            err.configure(text="⚠️ Fill all fields")
            return
        if np_ != cp:
            err.configure(text="⚠️ New passwords don't match")
            return
        ve = app._validate_master_password(np_)
        if ve:
            err.configure(text=ve)
            return

        # Any write still sitting in the app's deferred-save timer must land
        # before the salt rotates, or it would be re-encrypted with the old
        # key against the new salt.
        app._flush_pending_save()

        salt = get_or_create_salt()
        new_salt = os.urandom(32)
        err.configure(text="")
        status.configure(text="Deriving key and re-encrypting the vault…")
        set_busy(True)

        def finish(outcome: str):
            try:
                if not dlg.winfo_exists():
                    return
            except tk.TclError:
                return
            status.configure(text="")
            set_busy(False)
            if outcome == "bad_old":
                err.configure(text="⚠️ Current password is wrong")
                return
            if outcome != "ok":
                err.configure(text="⚠️ Could not save — try again")
                return
            dlg.destroy()

        def work():
            # Runs off the Tk thread: 480k-iteration PBKDF2 twice plus a
            # full vault re-encrypt would otherwise freeze the window.
            #
            # The rotation is completed here rather than in the UI callback
            # on purpose. Once the vault has been written under the new key,
            # the new salt *must* reach disk, otherwise the stored vault can
            # no longer be opened by any password. Deferring that step to a
            # callback would tie it to the dialog still being alive.
            old_key = app.key
            try:
                if not hmac.compare_digest(derive_key(op, salt), old_key):
                    app.root.after(0, lambda: finish("bad_old"))
                    return
                new_key = derive_key(np_, new_salt)
                save_data(app.data, new_key)
            except (OSError, ValueError) as exc:
                log.error("Re-encrypt during password change failed: %s",
                          exc, exc_info=True)
                app.root.after(0, lambda: finish("save_failed"))
                return
            try:
                rotate_salt(new_salt)
            except OSError as exc:
                # The vault on disk is now under the new key while the salt
                # still derives the old one. Put the old ciphertext back so
                # the vault stays openable with the unchanged password.
                log.error("Salt rotation failed: %s", exc, exc_info=True)
                try:
                    save_data(app.data, old_key)
                except (OSError, ValueError) as rb:
                    log.critical(
                        "Rollback after failed salt rotation failed: %s",
                        rb, exc_info=True)
                app.root.after(0, lambda: finish("rotate_failed"))
                return
            app.key = new_key
            log.info("Master password changed; salt rotated.")
            app.root.after(0, lambda: finish("ok"))

        threading.Thread(target=work, daemon=True).start()

    save_btn = ctk.CTkButton(
        frm, text="Change Password", height=38,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color=ORANGE, hover_color=ORANGE_HOVER, corner_radius=10,
        command=save)
    save_btn.pack(fill="x", padx=14)
    tip(save_btn, "Save the new master password")
    dlg.bind("<Return>", lambda _e: save())

    def close_if_idle(_e=None):
        # Re-encryption is already crash-safe, but closing mid-flight would
        # leave the user without any confirmation of what happened.
        if not busy["on"]:
            dlg.destroy()

    dlg.bind("<Escape>", close_if_idle)
    dlg.protocol("WM_DELETE_WINDOW", close_if_idle)
    old_e.focus()
