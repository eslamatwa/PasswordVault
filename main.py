"""
🔐 Password Vault - Modern password manager for Windows
"""

import customtkinter as ctk
import tkinter as tk
import json
import os
import base64
import threading

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import pyperclip
from PIL import Image, ImageDraw

# ─── Paths ────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(APP_DIR, "vault.dat")
SALT_FILE = os.path.join(APP_DIR, "vault.salt")

# ─── Category Emoji Map ──────────────────────────────────────
CAT_EMOJIS = {
    "General": "📂",
    "Social": "💬",
    "Work": "💼",
    "Banking": "🏦",
    "Gaming": "🎮",
    "Shopping": "🛒",
    "Email": "📧",
    "Cloud": "☁️",
    "VPN": "🔒",
    "Server": "🖥️",
    "Database": "🗄️",
    "API": "🔗",
    "Other": "📌",
}
DEFAULT_EMOJI = "📁"

# ─── Colors (Modern Dark) ────────────────────────────────────
BG_DARK = "#1a1b2e"
BG_CARD = "#242640"
BG_SIDEBAR = "#1e1f35"
BG_TOPBAR = "#1e1f35"
ACCENT = "#6c63ff"
ACCENT_HOVER = "#5a52e0"
GREEN = "#2dd4a8"
GREEN_HOVER = "#25b893"
BLUE = "#5b8ef5"
BLUE_HOVER = "#4a7de0"
RED = "#ff6b81"
RED_HOVER = "#e05a6e"
TEXT_PRIMARY = "#e8e8f0"
TEXT_SECONDARY = "#8888a8"
TEXT_DIM = "#5a5a7a"
BADGE_BG = "#32345a"
INPUT_BG = "#2a2c4a"
CARD_HOVER = "#2c2e50"


def cat_emoji(name):
    return CAT_EMOJIS.get(name, DEFAULT_EMOJI)


# ─── Encryption ───────────────────────────────────────────────
def get_or_create_salt():
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, "rb") as f:
            return f.read()
    salt = os.urandom(16)
    with open(SALT_FILE, "wb") as f:
        f.write(salt)
    return salt


def derive_key(password, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_data(data, key):
    return Fernet(key).encrypt(json.dumps(data, ensure_ascii=False).encode())


def decrypt_data(token, key):
    return json.loads(Fernet(key).decrypt(token).decode())


def save_data(data, key):
    with open(DATA_FILE, "wb") as f:
        f.write(encrypt_data(data, key))


def load_data(key):
    if not os.path.exists(DATA_FILE):
        return {"categories": ["General", "Social", "Work", "Banking"], "entries": []}
    with open(DATA_FILE, "rb") as f:
        return decrypt_data(f.read(), key)


# ─── Floating Widget (Popup Circle) ──────────────────────────
class FloatingWidget(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.title("Vault Widget")
        self.geometry("60x60+100+100")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", "#000001")
        self.config(bg="#000001")

        self.canvas = tk.Canvas(self, width=60, height=60, bg="#000001", highlightthickness=0)
        self.canvas.pack()

        # Draw circle
        self.canvas.create_oval(2, 2, 58, 58, fill=ACCENT, outline=ACCENT)
        self.canvas.create_text(30, 30, text="🔐", font=("Segoe UI Emoji", 24))

        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Button-3>", self.show_menu)

        self._drag_data = {"x": 0, "y": 0, "moved": False}

    def start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["moved"] = False

    def do_drag(self, event):
        if abs(event.x - self._drag_data["x"]) > 2 or abs(event.y - self._drag_data["y"]) > 2:
            self._drag_data["moved"] = True
        x = self.winfo_x() - self._drag_data["x"] + event.x
        y = self.winfo_y() - self._drag_data["y"] + event.y
        self.geometry(f"+{x}+{y}")

    def stop_drag(self, event):
        if not self._drag_data["moved"]:
            self.app.restore_window()

    def show_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open Vault", command=self.app.restore_window)
        menu.add_separator()
        menu.add_command(label="Exit", command=self.app.quit_app)
        menu.post(event.x_root, event.y_root)


# ═══════════════════════════════════════════════════════════════
class PasswordVault:
    def __init__(self):
        self.key = None
        self.data = None
        self.floating_widget = None
        self.current_category = "All"

        ctk.set_appearance_mode("dark")

        self.root = ctk.CTk()
        self.root.title("Password Vault")
        self.root.geometry("850x580")
        self.root.minsize(700, 500)
        self.root.configure(fg_color=BG_DARK)
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_widget)

        # Center
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 425
        y = (self.root.winfo_screenheight() // 2) - 290
        self.root.geometry(f"850x580+{x}+{y}")

        try:
            icon_path = os.path.join(APP_DIR, "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.show_login()

    # ─── Login Screen ────────────────────────────────────────
    def show_login(self):
        self.login_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.login_frame.place(relx=0.5, rely=0.45, anchor="center")

        # Glowing circle behind lock
        circle = ctk.CTkFrame(self.login_frame, width=100, height=100, corner_radius=50, fg_color=ACCENT)
        circle.pack(pady=(0, 16))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="🔐", font=ctk.CTkFont(size=44), fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.login_frame, text="Password Vault", font=ctk.CTkFont(size=32, weight="bold"), text_color=TEXT_PRIMARY).pack(pady=(0, 4))

        is_new = not os.path.exists(DATA_FILE)
        sub = "Create a master password" if is_new else "Enter your master password"
        ctk.CTkLabel(self.login_frame, text=sub, font=ctk.CTkFont(size=14), text_color=TEXT_SECONDARY).pack(pady=(0, 24))

        self.master_entry = ctk.CTkEntry(
            self.login_frame, width=320, height=46, placeholder_text="Master Password",
            show="●", font=ctk.CTkFont(size=14), justify="center",
            fg_color=INPUT_BG, border_color=TEXT_DIM, border_width=1, corner_radius=12,
        )
        self.master_entry.pack(pady=(0, 6))
        self.master_entry.bind("<Return>", lambda e: self.unlock())

        self.error_label = ctk.CTkLabel(self.login_frame, text="", text_color=RED, font=ctk.CTkFont(size=12))
        self.error_label.pack(pady=(0, 2))

        self.confirm_entry = None
        if is_new:
            self.confirm_entry = ctk.CTkEntry(
                self.login_frame, width=320, height=46, placeholder_text="Confirm Password",
                show="●", font=ctk.CTkFont(size=14), justify="center",
                fg_color=INPUT_BG, border_color=TEXT_DIM, border_width=1, corner_radius=12,
            )
            self.confirm_entry.pack(pady=(0, 10))
            self.confirm_entry.bind("<Return>", lambda e: self.unlock())

        ctk.CTkButton(
            self.login_frame, text="Unlock  🔓" if not is_new else "Create Vault  🔐",
            width=320, height=48, font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=12,
            command=self.unlock,
        ).pack(pady=(10, 0))

        self.master_entry.focus()

    def unlock(self):
        pw = self.master_entry.get()
        if not pw:
            self.error_label.configure(text="⚠️ Enter a password")
            return
        is_new = not os.path.exists(DATA_FILE)
        if is_new:
            c = self.confirm_entry.get() if self.confirm_entry else ""
            if pw != c:
                self.error_label.configure(text="⚠️ Passwords don't match")
                return
            if len(pw) < 4:
                self.error_label.configure(text="⚠️ Too short (min 4 chars)")
                return
        salt = get_or_create_salt()
        self.key = derive_key(pw, salt)
        try:
            self.data = load_data(self.key)
        except (InvalidToken, Exception):
            self.error_label.configure(text="⚠️ Wrong password")
            return
        if is_new:
            save_data(self.data, self.key)
        self.login_frame.destroy()
        self.build_ui()

    # ─── Main UI ─────────────────────────────────────────────
    def build_ui(self):
        # Top bar
        top = ctk.CTkFrame(self.root, height=54, fg_color=BG_TOPBAR, corner_radius=12)
        top.pack(fill="x", padx=14, pady=(12, 6))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="🔐", font=ctk.CTkFont(size=22)).pack(side="left", padx=(14, 6))
        ctk.CTkLabel(top, text="Password Vault", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY).pack(side="left")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_entries())
        ctk.CTkEntry(
            top, width=240, height=34, placeholder_text="🔍  Search...",
            textvariable=self.search_var, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=10,
        ).pack(side="left", padx=16)

        ctk.CTkButton(
            top, text="＋ Add New", width=120, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=self.show_add_dialog,
        ).pack(side="right", padx=14)

        # Content
        content = ctk.CTkFrame(self.root, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(4, 12))

        # Sidebar
        self.sidebar = ctk.CTkFrame(content, width=190, fg_color=BG_SIDEBAR, corner_radius=12)
        self.sidebar.pack(side="left", fill="y", padx=(0, 6))
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="Categories", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_SECONDARY).pack(pady=(16, 10), padx=12, anchor="w")

        self.cat_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", scrollbar_button_color=BG_SIDEBAR)
        self.cat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        ctk.CTkButton(
            self.sidebar, text="＋ Category", height=32,
            font=ctk.CTkFont(size=11), fg_color="transparent",
            border_width=1, border_color=TEXT_DIM, corner_radius=8,
            hover_color=CARD_HOVER, text_color=TEXT_SECONDARY,
            command=self.show_add_cat_dialog,
        ).pack(pady=(0, 10), padx=10, fill="x")

        # Entries
        self.entries_panel = ctk.CTkScrollableFrame(content, fg_color=BG_DARK, corner_radius=12, scrollbar_button_color=BG_CARD)
        self.entries_panel.pack(side="right", fill="both", expand=True)

        self.refresh_categories()
        self.refresh_entries()

    # ─── Categories ──────────────────────────────────────────
    def refresh_categories(self):
        for w in self.cat_frame.winfo_children():
            w.destroy()

        cats = ["All"] + self.data.get("categories", [])

        for cat in cats:
            if cat == "All":
                count = len(self.data["entries"])
                emoji = "🗂️"
            else:
                count = sum(1 for e in self.data["entries"] if e.get("category") == cat)
                emoji = cat_emoji(cat)

            active = cat == self.current_category
            btn = ctk.CTkButton(
                self.cat_frame,
                text=f" {emoji}  {cat}   ({count})",
                font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
                fg_color=ACCENT if active else "transparent",
                hover_color=ACCENT_HOVER if active else CARD_HOVER,
                text_color="white" if active else TEXT_PRIMARY,
                anchor="w", height=36, corner_radius=8,
                command=lambda c=cat: self.select_cat(c),
            )
            btn.pack(fill="x", pady=1)

            if cat != "All" and not active:
                pass

    def select_cat(self, cat):
        self.current_category = cat
        self.refresh_categories()
        self.refresh_entries()

    # ─── Entries ─────────────────────────────────────────────
    def refresh_entries(self):
        for w in self.entries_panel.winfo_children():
            w.destroy()

        search = self.search_var.get().lower() if hasattr(self, "search_var") else ""
        entries = list(self.data["entries"])

        if self.current_category != "All":
            entries = [e for e in entries if e.get("category") == self.current_category]
        if search:
            entries = [e for e in entries if
                       search in e.get("title", "").lower() or
                       search in e.get("username", "").lower() or
                       search in e.get("category", "").lower()]

        if not entries:
            empty_frame = ctk.CTkFrame(self.entries_panel, fg_color="transparent")
            empty_frame.pack(expand=True, fill="both")
            ctk.CTkLabel(empty_frame, text="📭", font=ctk.CTkFont(size=48)).pack(pady=(80, 8))
            ctk.CTkLabel(empty_frame, text="No passwords yet", font=ctk.CTkFont(size=16), text_color=TEXT_DIM).pack()
            ctk.CTkLabel(empty_frame, text="Click '＋ Add New' to get started", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(pady=(4, 0))
            return

        for entry in entries:
            self._card(entry)

    def _card(self, entry):
        card = ctk.CTkFrame(self.entries_panel, fg_color=BG_CARD, corner_radius=14)
        card.pack(fill="x", pady=4, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Row 1: Title + badge + actions
        r1 = ctk.CTkFrame(inner, fg_color="transparent")
        r1.pack(fill="x", pady=(0, 8))

        emoji = cat_emoji(entry.get("category", ""))
        ctk.CTkLabel(r1, text=f"{emoji}  {entry.get('title', '')}", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY).pack(side="left")

        ctk.CTkLabel(r1, text=entry.get("category", ""), font=ctk.CTkFont(size=10),
                      text_color=TEXT_SECONDARY, fg_color=BADGE_BG, corner_radius=6).pack(side="left", padx=(10, 0))

        # Actions
        ctk.CTkButton(r1, text="🗑", width=28, height=28, fg_color="transparent",
                       hover_color=RED_HOVER, corner_radius=6, font=ctk.CTkFont(size=13),
                       command=lambda: self.confirm_delete(entry)).pack(side="right", padx=2)
        ctk.CTkButton(r1, text="✏", width=28, height=28, fg_color="transparent",
                       hover_color=CARD_HOVER, corner_radius=6, font=ctk.CTkFont(size=13),
                       command=lambda: self.show_edit_dialog(entry)).pack(side="right", padx=2)

        # Row 2: Username
        r2 = ctk.CTkFrame(inner, fg_color="transparent")
        r2.pack(fill="x", pady=2)

        ctk.CTkLabel(r2, text="👤  User:", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY, width=80, anchor="w").pack(side="left")
        ctk.CTkLabel(r2, text=entry.get("username", ""), font=ctk.CTkFont(size=12), text_color=TEXT_PRIMARY, anchor="w").pack(side="left", padx=(2, 0))

        cu = ctk.CTkButton(r2, text="📋 Copy", width=75, height=26, font=ctk.CTkFont(size=10),
                            fg_color=GREEN, hover_color=GREEN_HOVER, text_color="#1a1b2e", corner_radius=8,
                            command=lambda: self._copy(entry.get("username", ""), cu))
        cu.pack(side="right")

        # Row 3: Password
        r3 = ctk.CTkFrame(inner, fg_color="transparent")
        r3.pack(fill="x", pady=2)

        ctk.CTkLabel(r3, text="🔒  Pass:", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY, width=80, anchor="w").pack(side="left")

        pwd = entry.get("password", "")
        dots = "●" * min(len(pwd), 18)
        plbl = ctk.CTkLabel(r3, text=dots, font=ctk.CTkFont(size=12), text_color=TEXT_PRIMARY, anchor="w")
        plbl.pack(side="left", padx=(2, 0))

        cp = ctk.CTkButton(r3, text="📋 Copy", width=75, height=26, font=ctk.CTkFont(size=10),
                            fg_color=BLUE, hover_color=BLUE_HOVER, text_color="white", corner_radius=8,
                            command=lambda: self._copy(pwd, cp))
        cp.pack(side="right")

        def toggle(lbl=plbl, real=pwd):
            if "●" in lbl.cget("text"):
                lbl.configure(text=real)
                eye.configure(text="🙈")
            else:
                lbl.configure(text="●" * min(len(real), 18))
                eye.configure(text="👁")

        eye = ctk.CTkButton(r3, text="👁", width=28, height=26, fg_color="transparent",
                             hover_color=CARD_HOVER, corner_radius=6, font=ctk.CTkFont(size=12), command=toggle)
        eye.pack(side="right", padx=(0, 6))

        # Row 4: Notes
        notes = entry.get("notes", "")
        if notes:
            r4 = ctk.CTkFrame(inner, fg_color="transparent")
            r4.pack(fill="x", pady=(6, 0))
            ctk.CTkLabel(r4, text="📝  Notes:", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY, width=80, anchor="nw").pack(side="left", anchor="n")
            ctk.CTkLabel(r4, text=notes, font=ctk.CTkFont(size=11), text_color=TEXT_DIM, anchor="w", wraplength=380, justify="left").pack(side="left", padx=(2, 0))

    def _copy(self, text, btn):
        pyperclip.copy(text)
        orig = btn.cget("text")
        orig_fg = btn.cget("fg_color")
        btn.configure(text="✅ Done!", fg_color="#22c55e")
        self.root.after(1000, lambda: btn.configure(text=orig, fg_color=orig_fg))

    # ─── Add Dialog (compact, modern) ────────────────────────
    def show_add_dialog(self):
        DW, DH = 390, 420
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Add Password")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG_DARK)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=ACCENT, height=38, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="＋  New Password", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").pack(side="left", padx=16)

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=20, pady=(8, 8))

        ctk.CTkLabel(frm, text="Title", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        title_e = ctk.CTkEntry(frm, height=30, font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        title_e.pack(fill="x", pady=(1, 4))

        ctk.CTkLabel(frm, text="Username", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        user_e = ctk.CTkEntry(frm, height=30, font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        user_e.pack(fill="x", pady=(1, 4))

        ctk.CTkLabel(frm, text="Password", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        pass_e = ctk.CTkEntry(frm, height=30, placeholder_text="Password", show="●",
                               font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        pass_e.pack(fill="x", pady=(1, 4))

        ctk.CTkLabel(frm, text="Category", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        cats = self.data.get("categories", ["General"])
        cat_cb = ctk.CTkComboBox(frm, values=cats, height=30, font=ctk.CTkFont(size=11),
                                  fg_color=INPUT_BG, border_width=0, corner_radius=7,
                                  button_color=ACCENT, button_hover_color=ACCENT_HOVER, dropdown_fg_color=BG_CARD)
        cat_cb.pack(fill="x", pady=(1, 4))
        if cats:
            cat_cb.set(cats[0])

        ctk.CTkLabel(frm, text="Notes", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        notes_tb = ctk.CTkTextbox(frm, height=42, font=ctk.CTkFont(size=11),
                                   fg_color=INPUT_BG, border_width=0, corner_radius=7)
        notes_tb.pack(fill="x", pady=(1, 6))

        # Error
        err = ctk.CTkLabel(frm, text="", text_color=RED, font=ctk.CTkFont(size=10), height=14)
        err.pack(pady=(0, 2))

        def save():
            t, u, p, c = title_e.get().strip(), user_e.get().strip(), pass_e.get().strip(), cat_cb.get().strip()
            n = notes_tb.get("1.0", "end").strip()
            if not t:
                err.configure(text="⚠️ Title is required")
                return
            if not p:
                err.configure(text="⚠️ Password is required")
                return
            self.data["entries"].append({"title": t, "username": u, "password": p, "category": c, "notes": n})
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        ctk.CTkButton(frm, text="💾  Save", height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8, command=save).pack(fill="x")

        title_e.focus()

    # ─── Edit Dialog ─────────────────────────────────────────
    def show_edit_dialog(self, entry):
        DW, DH = 390, 420
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Edit Password")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG_DARK)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        hdr = ctk.CTkFrame(dlg, fg_color=BLUE, height=38, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="✏  Edit Password", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").pack(side="left", padx=16)

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=20, pady=(10, 12))

        ctk.CTkLabel(frm, text="Title", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        title_e = ctk.CTkEntry(frm, height=30, font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        title_e.insert(0, entry.get("title", ""))
        title_e.pack(fill="x", pady=(1, 5))

        ctk.CTkLabel(frm, text="Username", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        user_e = ctk.CTkEntry(frm, height=30, font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        user_e.insert(0, entry.get("username", ""))
        user_e.pack(fill="x", pady=(1, 5))

        ctk.CTkLabel(frm, text="Password", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        pass_e = ctk.CTkEntry(frm, height=30, show="●", font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        pass_e.insert(0, entry.get("password", ""))
        pass_e.pack(fill="x", pady=(1, 5))

        ctk.CTkLabel(frm, text="Category", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        cats = self.data.get("categories", ["General"])
        cat_cb = ctk.CTkComboBox(frm, values=cats, height=30, font=ctk.CTkFont(size=11),
                                  fg_color=INPUT_BG, border_width=0, corner_radius=7,
                                  button_color=ACCENT, button_hover_color=ACCENT_HOVER, dropdown_fg_color=BG_CARD)
        cat_cb.set(entry.get("category", cats[0] if cats else ""))
        cat_cb.pack(fill="x", pady=(1, 5))

        ctk.CTkLabel(frm, text="Notes", font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(anchor="w")
        notes_tb = ctk.CTkTextbox(frm, height=42, font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0, corner_radius=7)
        notes_tb.insert("1.0", entry.get("notes", ""))
        notes_tb.pack(fill="x", pady=(1, 6))

        def save():
            entry["title"] = title_e.get().strip()
            entry["username"] = user_e.get().strip()
            entry["password"] = pass_e.get().strip()
            entry["category"] = cat_cb.get().strip()
            entry["notes"] = notes_tb.get("1.0", "end").strip()
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        ctk.CTkButton(frm, text="💾  Save Changes", height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color=BLUE, hover_color=BLUE_HOVER, corner_radius=8, command=save).pack(fill="x")

    # ─── Delete Confirm ──────────────────────────────────────
    def confirm_delete(self, entry):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Delete")
        dlg.geometry("360x180")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG_DARK)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, 360, 180)

        ctk.CTkLabel(dlg, text="⚠️  Are you sure?", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY).pack(pady=(22, 4))
        ctk.CTkLabel(dlg, text=f"Delete \"{entry.get('title', '')}\"?", font=ctk.CTkFont(size=13), text_color=TEXT_SECONDARY).pack(pady=(0, 16))

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=24)

        def do_del():
            self.data["entries"].remove(entry)
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        ctk.CTkButton(bf, text="🗑  Delete", fg_color=RED, hover_color=RED_HOVER,
                       width=145, height=38, font=ctk.CTkFont(size=13), corner_radius=8, command=do_del).pack(side="left", padx=4)
        ctk.CTkButton(bf, text="Cancel", fg_color=TEXT_DIM, hover_color=CARD_HOVER,
                       width=145, height=38, font=ctk.CTkFont(size=13), corner_radius=8, command=dlg.destroy).pack(side="right", padx=4)

    # ─── Add Category ────────────────────────────────────────
    def show_add_cat_dialog(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("New Category")
        dlg.geometry("360x190")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG_DARK)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, 360, 190)

        hdr = ctk.CTkFrame(dlg, fg_color=ACCENT, height=44, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📁  New Category", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").pack(side="left", padx=18)

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=24, pady=14)

        cat_e = ctk.CTkEntry(frm, height=38, placeholder_text="Category name",
                              font=ctk.CTkFont(size=13), fg_color=INPUT_BG, border_width=0, corner_radius=8)
        cat_e.pack(fill="x", pady=(0, 6))
        cat_e.focus()

        err = ctk.CTkLabel(frm, text="", text_color=RED, font=ctk.CTkFont(size=11))
        err.pack(pady=(0, 4))

        def save():
            name = cat_e.get().strip()
            if not name:
                err.configure(text="⚠️ Enter a name")
                return
            if name in self.data["categories"]:
                err.configure(text="⚠️ Already exists")
                return
            self.data["categories"].append(name)
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()

        cat_e.bind("<Return>", lambda e: save())
        ctk.CTkButton(frm, text="＋ Add", height=38, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8, command=save).pack(fill="x")

    # ─── Floating Widget Logic ───────────────────────────────
    def minimize_to_widget(self):
        self.root.withdraw()
        if not self.floating_widget:
            self.floating_widget = FloatingWidget(self)
        self.floating_widget.deiconify()

    def restore_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        
        if self.floating_widget:
            self.floating_widget.withdraw()

    def quit_app(self):
        self.root.destroy()

    # ─── Helpers ─────────────────────────────────────────────
    def _center(self, dlg, w, h):
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PasswordVault().run()
