"""Recycle Bin dialog — restore, permanent delete, empty all."""

from __future__ import annotations

import datetime
import logging
import uuid

import customtkinter as ctk

from ...i18n import anchor_start, justify_start, pad, side_end, side_start, t
from ...security import password_age_text
from ...settings import TRASH_DAYS
from ...theme import (
    BG_SEC, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    RED, RED_HOVER, TEXT_ON_GREEN, TEXT_PRI, TEXT_TERT, cat_emoji,
)
from ..widgets import dialog_header, tip

log = logging.getLogger("PasswordVault")


def _without(trash: list[dict], item: dict) -> list[dict]:
    """Return *trash* with exactly *item* removed.

    Matching on the id alone took every id-less row with it, so restoring
    one entry deleted before ids existed silently discarded the rest of
    them. Identity is the fallback whenever the id cannot single a row out.
    """
    item_id = item.get("id")
    if item_id and sum(1 for t in trash if t.get("id") == item_id) == 1:
        return [t for t in trash if t.get("id") != item_id]
    return [t for t in trash if t is not item]


def show(app) -> None:
    dlg = app._make_dialog("Recycle Bin", 460, 480)

    trash = app.data.get("trash", [])
    title_lbl = dialog_header(
        dlg, t("Recycle Bin  ({count} items)", count=len(trash)),
        icon="🗑️", pady=(14, 2))
    ctk.CTkLabel(
        dlg,
        text=t("Items are automatically deleted after {days} days",
               days=TRASH_DAYS),
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
        title_lbl.configure(
            text=t("🗑️  Recycle Bin  ({count} items)", count=count))
        if count:
            et_btn.pack(side=side_start(), fill="x", expand=True,
                        padx=pad(0, 4))
        else:
            et_btn.pack_forget()

    def refresh_list():
        for w in scroll.winfo_children():
            w.destroy()
        _update_header()
        trash_items = app.data.get("trash", [])
        if not trash_items:
            ctk.CTkLabel(scroll, text=t("🗑️  Empty"),
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
            text_color=TEXT_PRI, anchor=anchor_start(),
            wraplength=380, justify=justify_start()).pack(fill="x")

        del_at = item.get("deleted_at", "")
        age_t, _ = password_age_text(del_at)
        ctk.CTkLabel(
            inner,
            text=t("🗑️ Deleted {age}", age=age_t) if age_t else "",
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
            app.data["trash"] = _without(app.data["trash"], it)
            app._save_guarded()
            app.refresh_categories()
            app.refresh_entries()
            _drop_card(card)

        def perm_del(it=item, card=card):
            def do_perm(confirm):
                app.data["trash"] = _without(app.data["trash"], it)
                app._save_guarded()
                confirm.destroy()
                _drop_card(card)

            app._confirm(
                "Delete Forever?",
                t('"{title}"\nThis cannot be undone.',
              title=it.get("title", "")),
                icon="⚠️", confirm_text="Delete", on_confirm=do_perm,
                window_title="Delete Forever", size=(340, 190))

        r_btn = ctk.CTkButton(
            brow, text=t("♻️ Restore"), height=26,
            font=ctk.CTkFont(size=10), fg_color=GREEN,
            hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
            corner_radius=6, command=restore)
        r_btn.pack(side=side_start(), padx=pad(0, 4))
        tip(r_btn, t("Restore this entry back to the vault"))

        d_btn = ctk.CTkButton(
            brow, text=t("🗑️ Delete Forever"), height=26,
            font=ctk.CTkFont(size=10), fg_color=RED,
            hover_color=RED_HOVER, corner_radius=6,
            command=perm_del)
        d_btn.pack(side=side_start())
        tip(d_btn, t("Permanently delete this entry"))

    bot = ctk.CTkFrame(dlg, fg_color="transparent")
    bot.pack(fill="x", padx=14, pady=(0, 12))

    def empty_trash():
        def do_empty(confirm):
            app.data["trash"] = []
            app._save_guarded()
            log.info("Recycle bin emptied.")
            confirm.destroy()
            refresh_list()

        app._confirm(
            "Empty Recycle Bin?",
            t("Permanently delete all {count} items?\nThis action "
              "cannot be undone.",
              count=len(app.data.get("trash", []))),
            icon="⚠️", confirm_text="Delete All", on_confirm=do_empty,
            window_title="Empty Trash", size=(340, 190))

    et_btn = ctk.CTkButton(
        bot, text=t("🗑️  Empty Trash"), height=34,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=RED, hover_color=RED_HOVER,
        corner_radius=10, command=empty_trash)
    tip(et_btn, t("Permanently delete all items in trash"))

    ctk.CTkButton(
        bot, text=t("Close"), height=34,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(
        side=side_end(), fill="x", expand=True, padx=pad(4, 0))

    # Last: the first render also decides whether Empty Trash is shown.
    refresh_list()
