"""
Mini Vault — compact always-on-top password viewer.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
import customtkinter as ctk
import pyperclip

from ..theme import (
    BG, BG_SEC, BG_TERT, ACCENT, ACCENT_HOVER, GREEN,
    RED_HOVER, CARD_HOVER, TEAL, TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT,
    CARD_COLORS, cat_emoji, SEPARATOR,
)
from ..security import password_age_text
from .widgets import make_search_bar, tip


class MiniVault(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._mini_cat = "All"
        self.title("Mini Vault")
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

        ctk.CTkLabel(title_bar, text="🔐  Mini Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=12,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(side="left", padx=12)

        close_btn = ctk.CTkButton(title_bar, text="✕", width=28, height=28,
                                    font=ctk.CTkFont(size=13),
                                    fg_color="transparent",
                                    hover_color=RED_HOVER, corner_radius=6,
                                    text_color=TEXT_SEC, command=self._close)
        close_btn.pack(side="right", padx=(0, 4), pady=4)
        tip(close_btn, "Close Mini Vault")

        full_btn = ctk.CTkButton(title_bar, text="⬜", width=28, height=28,
                                   font=ctk.CTkFont(size=11),
                                   fg_color="transparent",
                                   hover_color=CARD_HOVER, corner_radius=6,
                                   text_color=TEXT_SEC, command=self._open_full)
        full_btn.pack(side="right", padx=(0, 2), pady=4)
        tip(full_btn, "Open full vault window")

        # Search
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        search = make_search_bar(
            self, self.search_var,
            lambda: (self.app.data.get("categories", [])
                     if self.app.data else []),
            self._set_cat)
        search.pack(fill="x", padx=10, pady=(8, 4))

        self._cat_label = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=10),
                                         text_color=ACCENT, height=14)
        self._cat_label.pack(padx=12, anchor="w")

        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BG_TERT)
        self.list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 8))
        self._refresh()

    # helpers
    def _set_cat(self, cat):
        self._mini_cat = cat
        self._cat_label.configure(
            text=f"📁 {cat}" if cat != "All" else "")
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
        search = self.search_var.get().lower()
        entries = list(self.app.data.get("entries", []))
        if self._mini_cat != "All":
            entries = [e for e in entries
                       if e.get("category") == self._mini_cat]
        if search:
            entries = [e for e in entries
                       if search in e.get("title", "").lower()
                       or search in e.get("username", "").lower()
                       or search in e.get("url", "").lower()
                       or search in e.get("notes", "").lower()]
        # pinned first
        entries.sort(key=lambda e: not e.get("pinned", False))
        if not entries:
            ctk.CTkLabel(self.list_frame, text="No results",
                          font=ctk.CTkFont(size=12),
                          text_color=TEXT_TERT).pack(pady=40)
            return
        for entry in entries:
            self._mini_card(entry)

    def _bind_right_click_recursive(self, widget, callback):
        """Bind right-click to a widget and ALL its children recursively."""
        widget.bind("<Button-3>", callback)
        try:
            for child in widget.winfo_children():
                self._bind_right_click_recursive(child, callback)
        except (tk.TclError, AttributeError):
            pass

    def _show_mini_context_menu(self, event, entry):
        """Show right-click context menu directly in Mini Vault."""
        menu = tk.Menu(self, tearoff=0,
                       bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT,
                       activeforeground="white",
                       font=("Segoe UI", 10),
                       relief="flat", bd=1)

        username = entry.get("username", "")
        password = entry.get("password", "")
        url = entry.get("url", "")

        menu.add_command(
            label="📋  Copy Username",
            command=lambda: self._mini_copy_text(username))
        menu.add_command(
            label="🔑  Copy Password",
            command=lambda: self._mini_copy_text(password))
        menu.add_separator()

        if url:
            menu.add_command(
                label="🌐  Open URL in Browser",
                command=lambda: webbrowser.open(url))
            menu.add_command(
                label="🌐  Open URL + Copy Username",
                command=lambda: (pyperclip.copy(username),
                                 webbrowser.open(url)))
        else:
            menu.add_command(label="🌐  Open URL in Browser",
                             state="disabled")
        menu.add_separator()

        menu.add_command(
            label="🖥️  SSH Session …",
            command=lambda: self.app._show_ssh_dialog(entry))
        menu.add_command(
            label="🖥️  RDP Session …",
            command=lambda: self.app._show_rdp_dialog(entry))
        menu.add_separator()

        menu.add_command(
            label="✏️  Edit Entry",
            command=lambda: self._mini_edit(entry))
        menu.add_command(
            label="📌  Pin / Unpin",
            command=lambda: (
                entry.update(pinned=not entry.get("pinned", False)),
                self.app._save_and_refresh()))
        menu.add_command(
            label="🗑️  Delete",
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

        if cc["strip"]:
            ctk.CTkFrame(card, width=4, fg_color=cc["strip"],
                          corner_radius=2).place(x=3, y=6, relheight=0.7)

        # Title row
        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")

        pin_icon = "📌 " if entry.get("pinned") else ""
        emoji = cat_emoji(entry.get("category", ""))
        ctk.CTkLabel(title_row,
                      text=f"{pin_icon}{emoji}  {entry.get('title', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=12,
                                        weight="bold"),
                      text_color=TEXT_PRI, anchor="w").pack(
            side="left", fill="x", expand=True)

        # Age
        age_t, age_c = password_age_text(
            entry.get("modified_at") or entry.get("created_at"))
        if age_t:
            ctk.CTkLabel(title_row, text=age_t,
                          font=ctk.CTkFont(size=9),
                          text_color=age_c).pack(side="right")

        if entry.get("username"):
            ctk.CTkLabel(inner, text=entry.get("username", ""),
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEXT_SEC, anchor="w").pack(
                fill="x", pady=(1, 4))
        else:
            ctk.CTkFrame(inner, height=4,
                          fg_color="transparent").pack()

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        cp_user = ctk.CTkButton(
            btn_row, text="📋 User", height=24, width=70,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
            text_color=TEXT_PRI,
            command=lambda: self._mini_copy(entry.get("username", ""),
                                            cp_user))
        cp_user.pack(side="left", padx=(0, 4))
        tip(cp_user, "Copy username to clipboard")

        cp_pass = ctk.CTkButton(
            btn_row, text="🔑 Pass", height=24, width=70,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=6,
            text_color="white",
            command=lambda: self._mini_copy(entry.get("password", ""),
                                            cp_pass))
        cp_pass.pack(side="left", padx=(0, 4))
        tip(cp_pass, "Copy password to clipboard")

        # URL button (only if URL exists)
        url = entry.get("url", "")
        if url:
            url_btn = ctk.CTkButton(
                btn_row, text="🌐", height=24, width=30,
                font=ctk.CTkFont(size=11),
                fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
                text_color=TEAL,
                command=lambda u=url: webbrowser.open(u))
            url_btn.pack(side="left", padx=(0, 4))
            tip(url_btn, f"Open {url}")

        edit_btn = ctk.CTkButton(
            btn_row, text="✏️", height=24, width=36,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
            text_color=TEXT_SEC,
            command=lambda: self._mini_edit(entry))
        edit_btn.pack(side="right")
        tip(edit_btn, "Edit this entry")

        # Apply right-click binding to card + ALL children recursively
        self.after(50, lambda: self._bind_right_click_recursive(
            card, _on_right_click))

    def _mini_edit(self, entry):
        self.app.restore_window()
        self.app.show_entry_dialog(entry)

    def _mini_copy(self, text, btn):
        self.app._copy_to_clipboard(text)
        orig = btn.cget("text")
        orig_fg = btn.cget("fg_color")
        btn.configure(text="✅ Copied!", fg_color=GREEN)
        self.after(1000, lambda: self._safe_cfg(btn, orig, orig_fg))

    @staticmethod
    def _safe_cfg(btn, t, fg):
        try:
            btn.configure(text=t, fg_color=fg)
        except (tk.TclError, ValueError):
            pass

