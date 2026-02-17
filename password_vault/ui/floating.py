"""
Floating Widget — draggable always-on-top bubble for quick access.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from ..theme import BG_SEC, ACCENT, TEXT_PRI


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
        self.canvas.create_oval(2, 2, 54, 54, fill=ACCENT, outline=ACCENT)
        self.canvas.create_text(28, 28, text="🔐",
                                 font=("Segoe UI Emoji", 22))

        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Button-3>", self.show_menu)
        self._drag_data = {"x": 0, "y": 0, "moved": False}

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
        menu = tk.Menu(self, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 10))
        menu.add_command(label="⬜  Open Full Vault",
                          command=self.app.restore_window)
        menu.add_command(label="📋  Mini Vault",
                          command=self.app.toggle_mini_vault)
        menu.add_separator()
        menu.add_command(label="✕  Exit", command=self.app.quit_app)
        menu.post(e.x_root, e.y_root)

