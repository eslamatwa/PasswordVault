"""Recycle Bin dialog — restore, permanent delete, empty all."""

from __future__ import annotations

import datetime
import logging

import customtkinter as ctk

from ...crypto import save_data
from ...security import password_age_text
from ...settings import TRASH_DAYS
from ...theme import (
    BG, BG_SEC, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    RED, RED_HOVER, TEXT_PRI, TEXT_SEC, TEXT_TERT, cat_emoji,
)
from ..widgets import tip

log = logging.getLogger("PasswordVault")


def show(app) -> None:
    dlg = app._make_dialog("Recycle Bin", 460, 480)

    trash = app.data.get("trash", [])
    ctk.CTkLabel(
        dlg,
        text=f"🗑️  Recycle Bin  ({len(trash)} items)",
        font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        text_color=TEXT_PRI).pack(pady=(14, 2))
    ctk.CTkLabel(
        dlg,
        text=f"Items are automatically deleted after {TRASH_DAYS} days",
        font=ctk.CTkFont(size=10), text_color=TEXT_TERT).pack(
        pady=(0, 8))

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                     scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    def refresh_list():
        for w in scroll.winfo_children():
            w.destroy()
        trash_items = app.data.get("trash", [])
        if not trash_items:
            ctk.CTkLabel(scroll, text="🗑️  Empty",
                          font=ctk.CTkFont(size=14),
                          text_color=TEXT_TERT).pack(pady=60)
            return
        for item in trash_items:
            _trash_card(item)

    def _trash_card(item):
        card = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=10)
        card.pack(fill="x", pady=3, padx=2)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        emoji = cat_emoji(item.get("category", ""))
        ctk.CTkLabel(
            inner, text=f"{emoji}  {item.get('title', '')}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRI, anchor="w").pack(fill="x")

        del_at = item.get("deleted_at", "")
        age_t, _ = password_age_text(del_at)
        ctk.CTkLabel(
            inner,
            text=f"🗑️ Deleted {age_t}" if age_t else "",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_TERT).pack(fill="x", pady=(2, 4))

        brow = ctk.CTkFrame(inner, fg_color="transparent")
        brow.pack(fill="x")

        def restore(it=item):
            it_copy = dict(it)
            it_copy.pop("deleted_at", None)
            it_copy["modified_at"] = (
                datetime.datetime.now().isoformat())
            app.data["entries"].append(it_copy)
            app.data["trash"] = [
                t for t in app.data["trash"]
                if t.get("id") != it.get("id")]
            save_data(app.data, app.key)
            app.refresh_categories()
            app.refresh_entries()
            refresh_list()

        def perm_del(it=item):
            confirm = ctk.CTkToplevel(dlg)
            confirm.title("Delete Forever")
            confirm.geometry("340x180")
            confirm.resizable(False, False)
            confirm.configure(fg_color=BG)
            confirm.transient(dlg)
            confirm.grab_set()
            app._center(confirm, 340, 180)
            confirm.bind("<Escape>", lambda _e: confirm.destroy())

            ctk.CTkLabel(
                confirm, text="⚠️  Delete Forever?",
                font=ctk.CTkFont(family="Segoe UI", size=16,
                                  weight="bold"),
                text_color=TEXT_PRI).pack(pady=(18, 4))
            ctk.CTkLabel(
                confirm,
                text=f'"{it.get("title", "")}"\n'
                     f"This cannot be undone.",
                font=ctk.CTkFont(size=12),
                text_color=TEXT_SEC, justify="center").pack(pady=(0, 14))

            cbf = ctk.CTkFrame(confirm, fg_color="transparent")
            cbf.pack(fill="x", padx=24)

            def do_perm():
                app.data["trash"] = [
                    t for t in app.data["trash"]
                    if t.get("id") != it.get("id")]
                save_data(app.data, app.key)
                confirm.destroy()
                refresh_list()

            ctk.CTkButton(
                cbf, text="Delete", fg_color=RED,
                hover_color=RED_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=do_perm).pack(side="left", padx=4)
            ctk.CTkButton(
                cbf, text="Cancel", fg_color=BG_TERT,
                hover_color=CARD_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=confirm.destroy).pack(side="right", padx=4)
            confirm.bind("<Return>", lambda _e: do_perm())

        r_btn = ctk.CTkButton(
            brow, text="♻️ Restore", height=26,
            font=ctk.CTkFont(size=10), fg_color=GREEN,
            hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=6, command=restore)
        r_btn.pack(side="left", padx=(0, 4))
        tip(r_btn, "Restore this entry back to the vault")

        d_btn = ctk.CTkButton(
            brow, text="🗑️ Delete Forever", height=26,
            font=ctk.CTkFont(size=10), fg_color=RED,
            hover_color=RED_HOVER, corner_radius=6,
            command=perm_del)
        d_btn.pack(side="left")
        tip(d_btn, "Permanently delete this entry")

    refresh_list()

    bot = ctk.CTkFrame(dlg, fg_color="transparent")
    bot.pack(fill="x", padx=14, pady=(0, 12))

    def empty_trash():
        confirm = ctk.CTkToplevel(dlg)
        confirm.title("Empty Trash")
        confirm.geometry("340x170")
        confirm.resizable(False, False)
        confirm.configure(fg_color=BG)
        confirm.transient(dlg)
        confirm.grab_set()
        app._center(confirm, 340, 170)

        ctk.CTkLabel(confirm, text="⚠️  Empty Recycle Bin?",
                      font=ctk.CTkFont(family="Segoe UI", size=16,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(18, 4))
        ctk.CTkLabel(
            confirm,
            text=f"Permanently delete all "
                 f"{len(app.data.get('trash', []))} "
                 f"items?\nThis action cannot be undone.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC, justify="center").pack(pady=(0, 14))

        cbf = ctk.CTkFrame(confirm, fg_color="transparent")
        cbf.pack(fill="x", padx=24)

        def do_empty():
            app.data["trash"] = []
            save_data(app.data, app.key)
            log.info("Recycle bin emptied.")
            confirm.destroy()
            refresh_list()

        ctk.CTkButton(
            cbf, text="Delete All", fg_color=RED,
            hover_color=RED_HOVER, width=130, height=34,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=do_empty).pack(side="left", padx=4)
        ctk.CTkButton(
            cbf, text="Cancel", fg_color=BG_TERT,
            hover_color=CARD_HOVER, width=130, height=34,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=confirm.destroy).pack(side="right", padx=4)
        confirm.bind("<Escape>", lambda _e: confirm.destroy())
        confirm.bind("<Return>", lambda _e: do_empty())

    if trash:
        et_btn = ctk.CTkButton(
            bot, text="🗑️  Empty Trash", height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=RED, hover_color=RED_HOVER,
            corner_radius=10, command=empty_trash)
        et_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tip(et_btn, "Permanently delete all items in trash")

    ctk.CTkButton(
        bot, text="Close", height=34,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(
        side="right", fill="x", expand=True, padx=(4, 0))
