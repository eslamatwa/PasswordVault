"""
Reusable UI widgets: Tooltip, iOS-style form helpers, search bar.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from ..theme import (
    BG_GROUP, BG_SEC, BG_TERT, SEPARATOR, ACCENT, ACCENT_HOVER,
    INPUT_BG, TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT,
    TT_BG, TT_FG, cat_emoji,
)


# ─── Tooltip System ──────────────────────────────────────────
class Tooltip:
    _active: Tooltip | None = None

    def __init__(self, widget, text: str, delay: int = 400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if Tooltip._active and Tooltip._active is not self:
            Tooltip._active._hide()
        if self._tip_window:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg=TT_BG)
        frame = tk.Frame(tw, bg=TT_BG, padx=10, pady=5)
        frame.pack()
        tk.Label(frame, text=self.text, bg=TT_BG, fg=TT_FG,
                 font=("Segoe UI", 10), wraplength=220, justify="left").pack()
        tw.update_idletasks()
        tw_w = tw.winfo_reqwidth()
        x = x - tw_w // 2
        screen_w = self.widget.winfo_screenwidth()
        if x + tw_w > screen_w - 8:
            x = screen_w - tw_w - 8
        if x < 8:
            x = 8
        tw.wm_geometry(f"+{x}+{y}")
        Tooltip._active = self

    def _hide(self):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None
        if Tooltip._active is self:
            Tooltip._active = None


def tip(widget, text: str) -> Tooltip:
    """Attach a tooltip to *widget*."""
    return Tooltip(widget, text)


# ─── iOS Group / Field Helpers ───────────────────────────────
def ios_group(parent, title: str | None = None, compact: bool = False):
    wrapper = ctk.CTkFrame(parent, fg_color="transparent")
    wrapper.pack(fill="x", pady=(0, 4 if compact else 8))
    if title:
        ctk.CTkLabel(wrapper, text=title.upper(),
                      font=ctk.CTkFont(family="Segoe UI", size=10),
                      text_color=TEXT_SEC, anchor="w").pack(
            anchor="w", padx=14, pady=(0, 2))
    group = ctk.CTkFrame(wrapper, fg_color=BG_GROUP, corner_radius=10)
    group.pack(fill="x")
    return group


def ios_field(group, label: str, idx: int = 0, show: str = "",
              placeholder: str = "", value: str = "",
              height: int = 34, is_textbox: bool = False):
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72, anchor="w").pack(side="left")
    if is_textbox:
        tb = ctk.CTkTextbox(row, height=height,
                             font=ctk.CTkFont(family="Segoe UI", size=12),
                             fg_color=INPUT_BG, border_width=0,
                             corner_radius=6, text_color=TEXT_PRI)
        tb.pack(side="left", fill="x", expand=True, padx=(4, 0))
        if value:
            tb.insert("1.0", value)
        return tb
    entry = ctk.CTkEntry(row, height=height,
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          placeholder_text=placeholder, text_color=TEXT_PRI,
                          **({} if not show else {"show": show}))
    entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
    if value:
        entry.insert(0, value)
    return entry


def ios_combo(group, label: str, values: list[str], current: str, idx: int = 0):
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72, anchor="w").pack(side="left")
    cb = ctk.CTkComboBox(row, values=values, height=30,
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                          dropdown_fg_color=BG_SEC, text_color=TEXT_PRI,
                          dropdown_text_color=TEXT_PRI)
    cb.pack(side="left", fill="x", expand=True, padx=(4, 0))
    if current:
        cb.set(current)
    return cb


# ─── Search Bar Widget ───────────────────────────────────────
def make_search_bar(parent, search_var, categories, on_category,
                    height: int = 32, width: int | None = None):
    frame = ctk.CTkFrame(parent, fg_color=BG_TERT, corner_radius=10,
                          height=height)
    if width:
        frame.configure(width=width)
    frame.pack_propagate(False)

    ctk.CTkLabel(frame, text="🔍", font=ctk.CTkFont(size=12), width=24,
                  text_color=TEXT_SEC).pack(side="left", padx=(8, 0))

    entry = ctk.CTkEntry(frame, textvariable=search_var, height=height - 4,
                          placeholder_text="Search passwords...",
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color="transparent", border_width=0,
                          text_color=TEXT_PRI, placeholder_text_color=TEXT_TERT)
    entry.pack(side="left", fill="x", expand=True, padx=(2, 0))
    frame._entry = entry  # store reference for focus shortcut

    def show_cat_menu():
        menu = tk.Menu(frame, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 10))
        menu.add_command(label="🗂️  All",
                          command=lambda: on_category("All"))
        menu.add_separator()
        for cat in categories():
            emoji = cat_emoji(cat)
            menu.add_command(label=f"{emoji}  {cat}",
                              command=lambda c=cat: on_category(c))
        try:
            menu.post(frame.winfo_rootx() + frame.winfo_width() - 30,
                      frame.winfo_rooty() + frame.winfo_height())
        except tk.TclError:
            pass

    cat_btn = ctk.CTkButton(frame, text="▼", width=28, height=height - 6,
                              font=ctk.CTkFont(size=10), fg_color="transparent",
                              hover_color=TEXT_QUAT, corner_radius=6,
                              text_color=TEXT_SEC, command=show_cat_menu)
    cat_btn.pack(side="right", padx=(0, 4))
    tip(cat_btn, "Filter by category")
    return frame

