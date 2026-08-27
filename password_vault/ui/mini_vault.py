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
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.app.data:
            return
        entries = filter_entries(
            self.app.data.get("entries", []), self._mini_cat,
            self.search_var.get())
        entries = sort_entries_pinned_first(entries)
        if not entries:
            ctk.CTkLabel(self.list_frame, text=t("No results"),
                          font=ui_font(12, family=None),
                          text_color=TEXT_TERT).pack(pady=40)
            return
        for entry in entries[:self._visible_limit]:
            self._mini_card(entry)
        hidden = len(entries) - self._visible_limit
        if hidden > 0:
            more = ctk.CTkButton(
                self.list_frame,
                text=t("⬇  Show more  ({hidden})", hidden=hidden),
                height=28, font=ui_font(10),
                fg_color=BG_SEC, hover_color=BG_TERT, corner_radius=6,
                text_color=TEXT_SEC, command=self._show_more)
            more.pack(fill="x", padx=2, pady=(4, 6))

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

        # SSH / RDP only when the entry looks like a remote host.
        if self.app._looks_remote(entry, url):
            menu.add_separator()
            menu.add_command(
                label=t("🖥️  SSH Session …"),
                command=lambda: self.app._show_ssh_dialog(entry))
            menu.add_command(
                label=t("🖥️  RDP Session …"),
                command=lambda: self.app._show_rdp_dialog(entry))
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
        color_key = entry.get("color", "default")
        cc = CARD_COLORS.get(color_key, CARD_COLORS["default"])

        card = ctk.CTkFrame(self.list_frame, fg_color=cc["bg"],
                              corner_radius=10)
        card.pack(fill="x", pady=3, padx=2)

        # Right-click context menu binding (applied recursively after build)
        def _on_right_click(event, e=entry):
            self._show_mini_context_menu(event, e)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)

        add_color_strip(card, cc, width=4, relheight=0.7)

        # Title row
        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")

        pin_icon = "📌 " if entry.get("pinned") else ""
        emoji = cat_emoji(entry.get("category", ""))
        full_title = entry.get("title", "")
        title_lbl = ctk.CTkLabel(
            title_row,
            text=f"{pin_icon}{emoji}  {elide(full_title, TITLE_MAX_CHARS)}",
            font=ui_font(12, "bold"), text_color=TEXT_PRI,
            anchor=anchor_start())
        title_lbl.pack(side=side_start(), fill="x", expand=True)
        if len(full_title) > TITLE_MAX_CHARS:
            tip(title_lbl, full_title)

        # Age
        age_t, age_c = password_age_text(
            entry.get("modified_at") or entry.get("created_at"))
        if age_t:
            ctk.CTkLabel(title_row, text=age_t,
                          font=ui_font(9, family=None),
                          text_color=age_c).pack(side=side_end())

        if entry.get("username"):
            ctk.CTkLabel(inner, text=entry.get("username", ""),
                          font=ui_font(10),
                          text_color=TEXT_SEC,
                          anchor=anchor_start()).pack(
                fill="x", pady=(1, 4))
        else:
            ctk.CTkFrame(inner, height=4,
                          fg_color="transparent").pack()

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        cp_user = ctk.CTkButton(
            btn_row, text=t("📋 User"), height=24, width=70,
            font=ui_font(10),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
            text_color=TEXT_PRI,
            command=lambda: self._mini_copy(entry.get("username", ""),
                                            cp_user))
        cp_user.pack(side=side_start(), padx=pad(0, 4))
        tip(cp_user, t("Copy username to clipboard"))

        cp_pass = ctk.CTkButton(
            btn_row, text=t("🔑 Pass"), height=24, width=70,
            font=ui_font(10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=6,
            text_color=TEXT_ON_ACCENT,
            command=lambda: self._mini_copy(entry.get("password", ""),
                                            cp_pass))
        cp_pass.pack(side=side_start(), padx=pad(0, 4))
        tip(cp_pass, t("Copy password to clipboard"))

        # URL button (only if URL exists)
        url = entry.get("url", "")
        if url:
            url_btn = ctk.CTkButton(
                btn_row, text="🌐", height=24, width=30,
                font=ui_font(11, family=None),
                fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
                text_color=TEAL,
                command=lambda u=url: self.app._open_url(u))
            url_btn.pack(side=side_start(), padx=pad(0, 4))
            tip(url_btn, t("Open {url}", url=url))

        edit_btn = ctk.CTkButton(
            btn_row, text="✏️", height=24, width=36,
            font=ui_font(11),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
            text_color=TEXT_SEC,
            command=lambda: self._mini_edit(entry))
        edit_btn.pack(side=side_end())
        tip(edit_btn, t("Edit this entry"))

        # Apply right-click binding to card + ALL children recursively.
        # Done synchronously here (the card is fully built above) — no
        # after-delay needed.
        bind_right_click_recursive(card, _on_right_click)

    def _mini_edit(self, entry):
        self.app.restore_window()
        self.app.show_entry_dialog(entry)

    def _mini_copy(self, text, btn):
        # The app helper owns both the flash restore timer and the clipboard
        # auto-clear schedule; duplicating them here leaked uncancelled
        # callbacks onto destroyed buttons.
        self.app._copy_to_clipboard(text, btn)

