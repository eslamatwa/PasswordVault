"""
Floating Widget — draggable always-on-top bubble for quick access.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from ..i18n import t
from ..theme import ACCENT, menu_style, resolve


class FloatingWidget(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.title("Vault Widget")
        self.geometry("56x56+100+100")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", "#000001")
        self.config(bg="#000001")

        self.canvas = tk.Canvas(self, width=56, height=56, bg="#000001",
                                 highlightthickness=0)
        self.canvas.pack()
        # A raw tk.Canvas takes one colour string, not a (light, dark) pair,
        # so the accent has to be resolved by hand — and re-resolved when
        # the mode changes. Resolving once at construction left the bubble
        # on the old accent until it was recreated.
        self._bubble = self.canvas.create_oval(2, 2, 54, 54)
        self.canvas.create_text(28, 28, text="🔐",
                                 font=("Segoe UI Emoji", 22))
        self._apply_theme()
        self._appearance = ctk.get_appearance_mode()
        self._watch_theme()

        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Button-3>", self.show_menu)
        self._drag_data = {"x": 0, "y": 0, "moved": False}

    def _apply_theme(self):
        accent = resolve(ACCENT)
        try:
            self.canvas.itemconfigure(self._bubble, fill=accent,
                                      outline=accent)
        except tk.TclError:
            pass

    def _watch_theme(self):
        """Repaint when the appearance mode changes.

        CustomTkinter re-picks a (light, dark) pair on its own widgets, but
        it has no hook to tell a plain canvas about the switch. Polling once
        a second is cheap next to the alternative — recreating the widget —
        and the bubble is the one surface that outlives a theme change,
        since it stays up while the main window is hidden.
        """
        current = ctk.get_appearance_mode()
        if current != self._appearance:
            self._appearance = current
            self._apply_theme()
        self._theme_timer = self.after(1000, self._watch_theme)

    def destroy(self):
        timer = getattr(self, "_theme_timer", None)
        if timer:
            try:
                self.after_cancel(timer)
            except (tk.TclError, ValueError):
                pass
            self._theme_timer = None
        super().destroy()

    def start_drag(self, e):
        self._drag_data.update(x=e.x, y=e.y, moved=False)

    def do_drag(self, e):
        if (abs(e.x - self._drag_data["x"]) > 2
                or abs(e.y - self._drag_data["y"]) > 2):
            self._drag_data["moved"] = True
        self.geometry(
            f"+{self.winfo_x() - self._drag_data['x'] + e.x}+"
            f"{self.winfo_y() - self._drag_data['y'] + e.y}")

    def stop_drag(self, e):
        if not self._drag_data["moved"]:
            self.app.toggle_mini_vault()

    def show_menu(self, e):
        menu = tk.Menu(self, tearoff=0, **menu_style())
        menu.add_command(label=t("⬜  Open Full Vault"),
                          command=self.app.restore_window)
        menu.add_command(label=t("📋  Mini Vault"),
                          command=self.app.toggle_mini_vault)
        menu.add_separator()
        menu.add_command(label=t("✕  Exit"), command=self._exit)
        menu.post(e.x_root, e.y_root)

    def _exit(self):
        """Confirm first: the vault is hidden here, so a stray click on Exit
        used to close everything with no warning."""
        self.app.restore_window()
        self.app.confirm_quit()

