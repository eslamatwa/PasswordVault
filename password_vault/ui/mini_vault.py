"""
Mini Vault — compact always-on-top password viewer.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from ..i18n import anchor_start, pad, side_end, side_start, t
from ..theme import (
    BG, BG_SEC, BG_TERT, ACCENT, ACCENT_HOVER,
    RED_HOVER, CARD_HOVER, TEAL, TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT,
    TEXT_ON_ACCENT, CARD_COLORS, cat_emoji, menu_style,
)
from ..security import password_age_text
from .widgets import (
    row_frame, row_label, icon_button, CardPool, card_signature,
    make_search_bar, tip, bind_right_click_recursive,
    add_color_strip, sort_entries_pinned_first, ui_font, elide,
    filter_entries,
)

# The Mini Vault card is narrower than the main one, so titles elide sooner.
TITLE_MAX_CHARS = 26

# Cards rendered per pass. The window is small, so a short page keeps
# keystroke-to-repaint fast on a large vault.
MINI_PAGE_SIZE = 15

# Idle time before a search keystroke triggers a rebuild.
SEARCH_DEBOUNCE_MS = 300


class MiniVault(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._mini_cat = "All"
        self._search_after_id = None
        self._visible_limit = MINI_PAGE_SIZE
        # The same card pool the main list uses. Rebuilding every row on
        # each keystroke costs far more than hiding and showing them.
        self._cards = CardPool(self._mini_card, card_signature,
                               fill="x", pady=3, padx=2)
        self._extras: list = []
        self.title(t("Mini Vault"))
        self.geometry("340x420")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=BG)
        self._drag_data = {"x": 0, "y": 0}

        # Title Bar
        title_bar = ctk.CTkFrame(self, height=36, fg_color=BG_SEC,
                                   corner_radius=0)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._do_drag)

        ctk.CTkLabel(title_bar, text=t("🔐  Mini Vault"),
                      font=ctk.CTkFont(family="Segoe UI", size=12,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(side=side_start(),
                                                padx=12)

        close_btn = ctk.CTkButton(title_bar, text="✕", width=28, height=28,
                                    font=ctk.CTkFont(size=13),
                                    fg_color="transparent",
                                    hover_color=RED_HOVER, corner_radius=6,
                                    text_color=TEXT_SEC, command=self._close)
        close_btn.pack(side=side_end(), padx=pad(0, 4), pady=4)
        tip(close_btn, t("Close Mini Vault"))

        full_btn = ctk.CTkButton(title_bar, text="⬜", width=28, height=28,
                                   font=ctk.CTkFont(size=11),
                                   fg_color="transparent",
                                   hover_color=CARD_HOVER, corner_radius=6,
                                   text_color=TEXT_SEC, command=self._open_full)
        full_btn.pack(side=side_end(), padx=pad(0, 2), pady=4)
        tip(full_btn, t("Open full vault window"))

        # Search
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write",
                                   lambda *_: self._debounced_refresh())
        search = make_search_bar(
            self, self.search_var,
            lambda: (self.app.data.get("categories", [])
                     if self.app.data else []),
            self._set_cat)
        search.pack(fill="x", padx=10, pady=(8, 4))

        self._cat_label = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=10),
                                         text_color=ACCENT, height=14)
        self._cat_label.pack(padx=12, anchor=anchor_start())

        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BG_TERT)
        self.list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 8))
        self._refresh()

    # helpers
    def _set_cat(self, cat):
        self._mini_cat = cat
        self._visible_limit = MINI_PAGE_SIZE
        self._cat_label.configure(
            text=f"📁 {cat}" if cat != "All" else "")
        self._refresh()

    def _debounced_refresh(self):
        """Rebuild once the user stops typing, not on every keystroke."""
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except (tk.TclError, ValueError):
                pass
        self._search_after_id = self.after(
            SEARCH_DEBOUNCE_MS, self._refresh_from_search)

    def _refresh_from_search(self):
        self._search_after_id = None
        self._visible_limit = MINI_PAGE_SIZE
        self._refresh()

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        self.geometry(
            f"+{self.winfo_x() - self._drag_data['x'] + event.x}+"
            f"{self.winfo_y() - self._drag_data['y'] + event.y}")

    def _close(self):
        self.withdraw()

    def _open_full(self):
        self.withdraw()
        self.app.restore_window()

    def _refresh(self):
        """Show the entries matching the category and search.

        Cards are kept and re-packed rather than rebuilt, for the same
        reason the main list does it: destroying and recreating a row of
        widgets costs far more than unmapping it.
        """
        for widget in self._extras:
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self._extras.clear()

        if not self.app.data:
            self._cards.clear()
            return

        entries = filter_entries(
            self.app.data.get("entries", []), self._mini_cat,
            self.search_var.get())
        entries = sort_entries_pinned_first(entries)

        live = {e.get("id") for e in self.app.data.get("entries", [])
                if e.get("id")}
        self._cards.keep_only(live)
        self._cards.hide_all()

        if not entries:
            empty = ctk.CTkLabel(self.list_frame, text=t("No results"),
                                  font=ui_font(12, family=None),
                                  text_color=TEXT_TERT)
            empty.pack(pady=40)
            self._extras.append(empty)
            return

        for entry in entries[:self._visible_limit]:
            self._cards.show(entry, entry.get("id"))
        hidden = len(entries) - self._visible_limit
        if hidden > 0:
            more = ctk.CTkButton(
                self.list_frame,
                text=t("⬇  Show more  ({hidden})", hidden=hidden),
                height=28, font=ui_font(10),
                fg_color=BG_SEC, hover_color=BG_TERT, corner_radius=6,
                text_color=TEXT_SEC, command=self._show_more)
            more.pack(fill="x", padx=2, pady=(4, 6))
            self._extras.append(more)

    def _show_more(self):
        self._visible_limit += MINI_PAGE_SIZE
        self._refresh()

    def _show_mini_context_menu(self, event, entry):
        """Show right-click context menu directly in Mini Vault."""
        menu = tk.Menu(self, tearoff=0, relief="flat", bd=1,
                       **menu_style())

        username = entry.get("username", "")
        password = entry.get("password", "")
        url = entry.get("url", "")

        menu.add_command(
            label=t("📋  Copy Username"),
            command=lambda: self._mini_copy_text(username))
        menu.add_command(
            label=t("🔑  Copy Password"),
            command=lambda: self._mini_copy_text(password))
        menu.add_separator()

        if url:
            menu.add_command(
                label=t("🌐  Open URL in Browser"),
                command=lambda: self.app._open_url(url))
            menu.add_command(
                label=t("🌐  Open URL + Copy Username"),
                command=lambda: (self._mini_copy_text(username),
                                 self.app._open_url(url)))
        else:
            menu.add_command(label=t("🌐  Open URL in Browser"),
                             state="disabled")

        # SSH / RDP, greyed out rather than hidden when the entry does
        # not look like a remote host -- the same rule and the same
        # wording as the main window's menu.
        menu.add_separator()
        self.app._add_remote_items(menu, entry, url)
        menu.add_separator()

        menu.add_command(
            label=t("✏️  Edit Entry"),
            command=lambda: self._mini_edit(entry))
        menu.add_command(
            label=t("📌  Pin / Unpin"),
            command=lambda: (
                entry.update(pinned=not entry.get("pinned", False)),
                self.app._save_and_refresh()))
        menu.add_command(
            label=t("🗑️  Delete"),
            command=lambda: self.app.confirm_delete(entry))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _mini_copy_text(self, text):
        """Copy text to clipboard with auto-clear support."""
        self.app._copy_to_clipboard(text)

    def _mini_card(self, entry):
        """One row of the Mini Vault.

        Plain Tk widgets, for the same reason the main list uses them: a
        CustomTkinter widget draws itself onto its own canvas, which costs
        9x a tk.Label for text and 35-50x for a button or frame. The card
        keeps its CTkFrame, because the rounded tint is the visible part.
        """
        color_key = entry.get("color", "default")
        cc = CARD_COLORS.get(color_key, CARD_COLORS["default"])
        bg = cc["bg"]

        card = ctk.CTkFrame(self.list_frame, fg_color=bg,
                              corner_radius=10)
        # Not packed here: the pool owns where it goes, so a cached card
        # can be hidden and re-shown without being rebuilt.

        # Right-click context menu binding (applied recursively after build)
        def _on_right_click(event, e=entry):
            self._show_mini_context_menu(event, e)

        inner = row_frame(card, bg, fill="x", padx=10, pady=7)
        add_color_strip(card, cc, width=4, relheight=0.7)

        # Title row
        title_row = row_frame(inner, bg, fill="x")

        pin_icon = "📌 " if entry.get("pinned") else ""
        emoji = cat_emoji(entry.get("category", ""))
        full_title = entry.get("title", "")
        title_lbl = row_label(
            title_row,
            f"{pin_icon}{emoji}  {elide(full_title, TITLE_MAX_CHARS)}",
            bg, TEXT_PRI, font=("Segoe UI", 10, "bold"),
            side=side_start(), fill="x", expand=True)
        title_lbl.configure(anchor=anchor_start())
        if len(full_title) > TITLE_MAX_CHARS:
            tip(title_lbl, full_title)

        # Age
        age_t, age_c = password_age_text(
            entry.get("modified_at") or entry.get("created_at"))
        if age_t:
            row_label(title_row, age_t, bg, age_c,
                      font=("Segoe UI", 8), side=side_end())

        username = entry.get("username", "")
        if username:
            row_label(inner, username, bg, TEXT_SEC,
                      font=("Segoe UI", 8),
                      fill="x", pady=(1, 4)).configure(
                          anchor=anchor_start())
        else:
            row_frame(inner, bg, pady=2)

        btn_row = row_frame(inner, bg, fill="x")

        cp_user = icon_button(
            btn_row, t("📋 User"), None, bg=BG_TERT, hover=TEXT_QUAT,
            fg=TEXT_PRI, font=("Segoe UI", 8),
            side=side_start(), padx=pad(0, 4))
        cp_user.bind("<Button-1>",
                     lambda _e: self._mini_copy(username, cp_user),
                     add="+")
        tip(cp_user, t("Copy username to clipboard"))

        password = entry.get("password", "")
        cp_pass = icon_button(
            btn_row, t("🔑 Pass"), None, bg=ACCENT, hover=ACCENT_HOVER,
            fg=TEXT_ON_ACCENT, font=("Segoe UI", 8),
            side=side_start(), padx=pad(0, 4))
        cp_pass.bind("<Button-1>",
                     lambda _e: self._mini_copy(password, cp_pass),
                     add="+")
        tip(cp_pass, t("Copy password to clipboard"))

        # URL button (only if URL exists)
        url = entry.get("url", "")
        if url:
            url_btn = icon_button(
                btn_row, "🌐", lambda u=url: self.app._open_url(u),
                bg=BG_TERT, hover=TEXT_QUAT, fg=TEAL,
                side=side_start(), padx=pad(0, 4))
            tip(url_btn, t("Open {url}", url=url))

        edit_btn = icon_button(
            btn_row, "✏️", lambda: self._mini_edit(entry),
            bg=BG_TERT, hover=TEXT_QUAT, fg=TEXT_SEC, side=side_end())
        tip(edit_btn, t("Edit this entry"))

        # Apply right-click binding to card + ALL children recursively.
        # Done synchronously here (the card is fully built above) — no
        # after-delay needed.
        bind_right_click_recursive(card, _on_right_click)
        return card

    def _mini_edit(self, entry):
        self.app.restore_window()
        self.app.show_entry_dialog(entry)

    def _mini_copy(self, text, btn):
        # The app helper owns both the flash restore timer and the clipboard
        # auto-clear schedule; duplicating them here leaked uncancelled
        # callbacks onto destroyed buttons.
        self.app._copy_to_clipboard(text, btn)

