"""Recycle Bin dialog — restore, permanent delete, empty all."""

from __future__ import annotations

import datetime
import logging
import uuid

import customtkinter as ctk

from ...security import password_age_text
from ...settings import TRASH_DAYS
from ...theme import (
    BG, BG_SEC, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    RED, RED_HOVER, TEXT_ON_GREEN, TEXT_PRI, TEXT_SEC, TEXT_TERT, cat_emoji,
)
from ..widgets import modal_child, tip

log = logging.getLogger("PasswordVault")


def show(app) -> None:
    dlg = app._make_dialog("Recycle Bin", 460, 480)

    trash = app.data.get("trash", [])
    title_lbl = ctk.CTkLabel(
        dlg,
        text=f"🗑️  Recycle Bin  ({len(trash)} items)",
        font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        text_color=TEXT_PRI)
    title_lbl.pack(pady=(14, 2))
    ctk.CTkLabel(
        dlg,
        text=f"Items are automatically deleted after {TRASH_DAYS} days",
        font=ctk.CTkFont(size=10), text_color=TEXT_TERT).pack(
        pady=(0, 8))

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                     scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    def _update_header():
        """Keep the count and the Empty button in step with the bin.

        Both used to be decided once when the dialog opened, so the header
        still claimed items after the last one was restored.
        """
        count = len(app.data.get("trash", []))
        title_lbl.configure(text=f"🗑️  Recycle Bin  ({count} items)")
        if count:
            et_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        else:
            et_btn.pack_forget()

    def refresh_list():
        for w in scroll.winfo_children():
            w.destroy()
        _update_header()
        trash_items = app.data.get("trash", [])
        if not trash_items:
            ctk.CTkLabel(scroll, text="🗑️  Empty",
                          font=ctk.CTkFont(size=14),
                          text_color=TEXT_TERT).pack(pady=60)
            return
        for item in trash_items:
            _trash_card(item)

    def _drop_card(card):
        # Only the affected row is gone; rebuilding every card here would
        # redraw the whole bin for a single restore/delete.
        card.destroy()
        _update_header()
        if not app.data.get("trash", []):
            refresh_list()

    def _trash_card(item):
        card = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=10)
        card.pack(fill="x", pady=3, padx=2)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        emoji = cat_emoji(item.get("category", ""))
        ctk.CTkLabel(
            inner, text=f"{emoji}  {item.get('title', '')}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRI, anchor="w",
            wraplength=380, justify="left").pack(fill="x")

        del_at = item.get("deleted_at", "")
        age_t, _ = password_age_text(del_at)
        ctk.CTkLabel(
            inner,
            text=f"🗑️ Deleted {age_t}" if age_t else "",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_TERT).pack(fill="x", pady=(2, 4))

        brow = ctk.CTkFrame(inner, fg_color="transparent")
        brow.pack(fill="x")

        def restore(it=item, card=card):
            it_copy = dict(it)
            it_copy.pop("deleted_at", None)
            it_copy["modified_at"] = (
                datetime.datetime.now().isoformat())
            # A restored id can already be live (restore, edit, delete again,
            # restore the older copy); two entries sharing an id would make
            # edit and delete act on the wrong one.
            live_ids = {e.get("id") for e in app.data["entries"]}
            if not it_copy.get("id") or it_copy["id"] in live_ids:
                it_copy["id"] = str(uuid.uuid4())
            app.data["entries"].append(it_copy)
            app.data["trash"] = [
                t for t in app.data["trash"]
                if t.get("id") != it.get("id")]
            app._save_guarded()
            app.refresh_categories()
            app.refresh_entries()
            _drop_card(card)

        def perm_del(it=item, card=card):
            confirm = ctk.CTkToplevel(dlg)
            confirm.title("Delete Forever")
            confirm.geometry("340x180")
            confirm.resizable(False, False)
            confirm.configure(fg_color=BG)
            modal_child(dlg, confirm)
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
                app._save_guarded()
                confirm.destroy()
                _drop_card(card)

            ctk.CTkButton(
                cbf, text="Delete", fg_color=RED,
                hover_color=RED_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=do_perm).pack(side="left", padx=4)
            cancel = ctk.CTkButton(
                cbf, text="Cancel", fg_color=BG_TERT,
                hover_color=CARD_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=confirm.destroy)
            cancel.pack(side="right", padx=4)
            # Enter cancels; permanent deletion takes a deliberate click.
            confirm.bind("<Return>", lambda _e: confirm.destroy())
            cancel.focus()

        r_btn = ctk.CTkButton(
            brow, text="♻️ Restore", height=26,
            font=ctk.CTkFont(size=10), fg_color=GREEN,
            hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
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

    bot = ctk.CTkFrame(dlg, fg_color="transparent")
    bot.pack(fill="x", padx=14, pady=(0, 12))

    def empty_trash():
        confirm = ctk.CTkToplevel(dlg)
        confirm.title("Empty Trash")
        confirm.geometry("340x170")
        confirm.resizable(False, False)
        confirm.configure(fg_color=BG)
        modal_child(dlg, confirm)
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
            app._save_guarded()
            log.info("Recycle bin emptied.")
            confirm.destroy()
            refresh_list()

        ctk.CTkButton(
            cbf, text="Delete All", fg_color=RED,
            hover_color=RED_HOVER, width=130, height=34,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=do_empty).pack(side="left", padx=4)
        cancel = ctk.CTkButton(
            cbf, text="Cancel", fg_color=BG_TERT,
            hover_color=CARD_HOVER, width=130, height=34,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=confirm.destroy)
        cancel.pack(side="right", padx=4)
        confirm.bind("<Escape>", lambda _e: confirm.destroy())
        # Enter cancels; emptying the bin takes a deliberate click.
        confirm.bind("<Return>", lambda _e: confirm.destroy())
        cancel.focus()

    et_btn = ctk.CTkButton(
        bot, text="🗑️  Empty Trash", height=34,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=RED, hover_color=RED_HOVER,
        corner_radius=10, command=empty_trash)
    tip(et_btn, "Permanently delete all items in trash")

    ctk.CTkButton(
        bot, text="Close", height=34,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(
        side="right", fill="x", expand=True, padx=(4, 0))

    # Last: the first render also decides whether Empty Trash is shown.
    refresh_list()
