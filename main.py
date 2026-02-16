"""
🔐 Password Vault - Modern password manager for Windows (Apple Dark Style)
"""

APP_VERSION = "2.0"
APP_AUTHOR = "Eslam Atwa"

import customtkinter as ctk
import tkinter as tk
import json
import os
import sys
import shutil
import base64
import uuid
import string
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import pyperclip

# ─── Paths ────────────────────────────────────────────────────
# Use %APPDATA%/PasswordVault for persistent, safe data storage
_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
DATA_DIR = os.path.join(_APPDATA, "PasswordVault")
os.makedirs(DATA_DIR, exist_ok=True)

# Migrate old data from exe directory if it exists (one-time)
_EXE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))
for _fname in ("vault.dat", "vault.salt"):
    _old = os.path.join(_EXE_DIR, _fname)
    _new = os.path.join(DATA_DIR, _fname)
    if os.path.exists(_old) and not os.path.exists(_new):
        shutil.copy2(_old, _new)

DATA_FILE = os.path.join(DATA_DIR, "vault.dat")
SALT_FILE = os.path.join(DATA_DIR, "vault.salt")
APP_DIR = _EXE_DIR  # for icon.ico lookup

# ─── Constants (defaults, overridden by settings) ─────────────
AUTO_LOCK_MINUTES = 5
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 30

# ─── Settings Persistence ────────────────────────────────────
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "auto_lock_minutes": 5,
    "gen_length": 16,
    "gen_upper": True,
    "gen_lower": True,
    "gen_digits": True,
    "gen_symbols": True,
    "start_minimized": False,
    "default_card_color": "default",
    "max_login_attempts": 5,
    "lockout_seconds": 30,
    "clipboard_clear_seconds": 0,   # 0 = off
}


def load_settings():
    """Load settings from JSON, falling back to defaults."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(saved)
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    """Persist settings to JSON."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

# ─── Category Emoji Map ──────────────────────────────────────
CAT_EMOJIS = {
    "General": "📂", "Social": "💬", "Work": "💼", "Banking": "🏦",
    "Gaming": "🎮", "Shopping": "🛒", "Email": "📧", "Cloud": "☁️",
    "VPN": "🔒", "Server": "🖥️", "Database": "🗄️", "API": "🔗", "Other": "📌",
}
DEFAULT_EMOJI = "📁"

# ─── Card Color Presets (subtle tints) ───────────────────────
CARD_COLORS = {
    "default": {"bg": "#2c2c2e", "strip": None,      "label": "Default"},
    "blue":    {"bg": "#22283a", "strip": "#0a84ff",  "label": "Blue"},
    "green":   {"bg": "#222e26", "strip": "#30d158",  "label": "Green"},
    "red":     {"bg": "#2e2426", "strip": "#ff453a",  "label": "Red"},
    "orange":  {"bg": "#2e2a24", "strip": "#ff9f0a",  "label": "Orange"},
    "purple":  {"bg": "#28242e", "strip": "#bf5af2",  "label": "Purple"},
    "teal":    {"bg": "#22282e", "strip": "#64d2ff",  "label": "Teal"},
    "yellow":  {"bg": "#2e2d22", "strip": "#ffd60a",  "label": "Yellow"},
    "pink":    {"bg": "#2e2428", "strip": "#ff6482",  "label": "Pink"},
}

# ─── Colors (Apple Dark Mode) ────────────────────────────────
BG          = "#1c1c1e"
BG_SEC      = "#2c2c2e"
BG_TERT     = "#3a3a3c"
BG_GROUP    = "#2c2c2e"
SEPARATOR   = "#38383a"

ACCENT      = "#0a84ff"
ACCENT_HOVER = "#0070e0"
GREEN       = "#30d158"
GREEN_HOVER = "#28b84c"
RED         = "#ff453a"
RED_HOVER   = "#e03e35"
ORANGE      = "#ff9f0a"
ORANGE_HOVER = "#e08e09"
YELLOW      = "#ffd60a"
TEAL        = "#64d2ff"
PURPLE      = "#bf5af2"

TEXT_PRI    = "#ffffff"
TEXT_SEC    = "#8e8e93"
TEXT_TERT   = "#636366"
TEXT_QUAT   = "#48484a"

BADGE_BG    = "#3a3a3c"
INPUT_BG    = "#1c1c1e"
CARD_HOVER  = "#3a3a3c"
SIDEBAR_BG  = "#2c2c2e"
SIDEBAR_SEL = "#0a84ff"

# Tooltip styling
TT_BG       = "#48484a"
TT_FG       = "#ffffff"


def cat_emoji(name):
    return CAT_EMOJIS.get(name, DEFAULT_EMOJI)


# ─── Tooltip System ──────────────────────────────────────────
class Tooltip:
    """Hover tooltip for any widget — shows a brief description."""
    _active = None

    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip_window = None
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
        except Exception:
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


def tip(widget, text):
    """Shorthand to attach a tooltip to a widget."""
    return Tooltip(widget, text)


# ─── Password Strength ───────────────────────────────────────
def password_strength(pw):
    if not pw:
        return 0, "", TEXT_QUAT
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    if any(c.isupper() for c in pw) and any(c.islower() for c in pw):
        score += 1
    if any(c.isdigit() for c in pw):
        score += 0.5
    if any(c in string.punctuation for c in pw):
        score += 0.5
    score = min(int(score), 4)
    labels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Strong", 4: "Very Strong"}
    colors = {0: RED, 1: RED, 2: ORANGE, 3: GREEN, 4: GREEN}
    return score, labels[score], colors[score]


# ─── Password Generator (cryptographically secure) ──────────
def generate_password(length=16, upper=True, lower=True, digits=True, symbols=True):
    chars = ""
    required = []
    if upper:
        chars += string.ascii_uppercase
        required.append(secrets.choice(string.ascii_uppercase))
    if lower:
        chars += string.ascii_lowercase
        required.append(secrets.choice(string.ascii_lowercase))
    if digits:
        chars += string.digits
        required.append(secrets.choice(string.digits))
    if symbols:
        chars += string.punctuation
        required.append(secrets.choice(string.punctuation))
    if not chars:
        chars = string.ascii_letters + string.digits
    pw = required + [secrets.choice(chars) for _ in range(max(length - len(required), 0))]
    for i in range(len(pw) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pw[i], pw[j] = pw[j], pw[i]
    return "".join(pw)


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
    tmp = DATA_FILE + ".tmp"
    try:
        encrypted = encrypt_data(data, key)
        with open(tmp, "wb") as f:
            f.write(encrypted)
        os.replace(tmp, DATA_FILE)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_data(key):
    if not os.path.exists(DATA_FILE):
        return {"categories": ["General", "Social", "Work", "Banking"], "entries": []}
    with open(DATA_FILE, "rb") as f:
        data = decrypt_data(f.read(), key)
    changed = False
    for entry in data.get("entries", []):
        if "id" not in entry:
            entry["id"] = str(uuid.uuid4())
            changed = True
    if changed:
        save_data(data, key)
    return data


# ─── iOS Group / Field Helpers ───────────────────────────────
def ios_group(parent, title=None, compact=False):
    wrapper = ctk.CTkFrame(parent, fg_color="transparent")
    wrapper.pack(fill="x", pady=(0, 4 if compact else 8))
    if title:
        ctk.CTkLabel(wrapper, text=title.upper(), font=ctk.CTkFont(family="Segoe UI", size=10),
                      text_color=TEXT_SEC, anchor="w").pack(anchor="w", padx=14, pady=(0, 2))
    group = ctk.CTkFrame(wrapper, fg_color=BG_GROUP, corner_radius=10)
    group.pack(fill="x")
    return group


def ios_field(group, label, idx=0, show="", placeholder="", value="", height=34, is_textbox=False):
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72, anchor="w").pack(side="left")
    if is_textbox:
        tb = ctk.CTkTextbox(row, height=height, font=ctk.CTkFont(family="Segoe UI", size=12),
                             fg_color=INPUT_BG, border_width=0, corner_radius=6, text_color=TEXT_PRI)
        tb.pack(side="left", fill="x", expand=True, padx=(4, 0))
        if value:
            tb.insert("1.0", value)
        return tb
    entry = ctk.CTkEntry(row, height=height, font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          placeholder_text=placeholder, text_color=TEXT_PRI,
                          **({} if not show else {"show": show}))
    entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
    if value:
        entry.insert(0, value)
    return entry


def ios_combo(group, label, values, current, idx=0):
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72, anchor="w").pack(side="left")
    cb = ctk.CTkComboBox(row, values=values, height=30, font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                          dropdown_fg_color=BG_SEC, text_color=TEXT_PRI, dropdown_text_color=TEXT_PRI)
    cb.pack(side="left", fill="x", expand=True, padx=(4, 0))
    if current:
        cb.set(current)
    return cb


# ─── Search Bar Widget ───────────────────────────────────────
def make_search_bar(parent, search_var, categories, on_category, height=32, width=None):
    """Create a styled search bar with icon, placeholder and category filter button."""
    frame = ctk.CTkFrame(parent, fg_color=BG_TERT, corner_radius=10, height=height)
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

    def show_cat_menu():
        menu = tk.Menu(frame, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 10))
        menu.add_command(label="🗂️  All", command=lambda: on_category("All"))
        menu.add_separator()
        for cat in categories():
            emoji = cat_emoji(cat)
            menu.add_command(label=f"{emoji}  {cat}", command=lambda c=cat: on_category(c))
        try:
            menu.post(frame.winfo_rootx() + frame.winfo_width() - 30,
                      frame.winfo_rooty() + frame.winfo_height())
        except Exception:
            pass

    cat_btn = ctk.CTkButton(frame, text="▼", width=28, height=height - 6,
                              font=ctk.CTkFont(size=10), fg_color="transparent",
                              hover_color=TEXT_QUAT, corner_radius=6, text_color=TEXT_SEC,
                              command=show_cat_menu)
    cat_btn.pack(side="right", padx=(0, 4))
    tip(cat_btn, "Filter by category")

    return frame


# ─── Mini Vault ──────────────────────────────────────────────
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
        title_bar = ctk.CTkFrame(self, height=36, fg_color=BG_SEC, corner_radius=0)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._do_drag)

        ctk.CTkLabel(title_bar, text="🔐  Mini Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                      text_color=TEXT_PRI).pack(side="left", padx=12)

        close_btn = ctk.CTkButton(title_bar, text="✕", width=28, height=28,
                       font=ctk.CTkFont(size=13), fg_color="transparent",
                       hover_color=RED_HOVER, corner_radius=6, text_color=TEXT_SEC,
                       command=self._close)
        close_btn.pack(side="right", padx=(0, 4), pady=4)
        tip(close_btn, "Close Mini Vault")

        full_btn = ctk.CTkButton(title_bar, text="⬜", width=28, height=28,
                       font=ctk.CTkFont(size=11), fg_color="transparent",
                       hover_color=CARD_HOVER, corner_radius=6, text_color=TEXT_SEC,
                       command=self._open_full)
        full_btn.pack(side="right", padx=(0, 2), pady=4)
        tip(full_btn, "Open full vault window")

        # Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        search = make_search_bar(self, self.search_var,
                                  lambda: self.app.data.get("categories", []) if self.app.data else [],
                                  self._set_cat)
        search.pack(fill="x", padx=10, pady=(8, 4))

        # Category indicator
        self._cat_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=10),
                                         text_color=ACCENT, height=14)
        self._cat_label.pack(padx=12, anchor="w")

        # List
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                                   scrollbar_button_color=BG_TERT)
        self.list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 8))
        self._refresh()

    def _set_cat(self, cat):
        self._mini_cat = cat
        self._cat_label.configure(text=f"📁 {cat}" if cat != "All" else "")
        self._refresh()

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        self.geometry(f"+{self.winfo_x() - self._drag_data['x'] + event.x}+"
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
            entries = [e for e in entries if e.get("category") == self._mini_cat]
        if search:
            entries = [e for e in entries if
                       search in e.get("title", "").lower() or
                       search in e.get("username", "").lower()]
        if not entries:
            ctk.CTkLabel(self.list_frame, text="No results",
                          font=ctk.CTkFont(size=12), text_color=TEXT_TERT).pack(pady=40)
            return
        for entry in entries:
            self._mini_card(entry)

    def _mini_card(self, entry):
        color_key = entry.get("color", "default")
        cc = CARD_COLORS.get(color_key, CARD_COLORS["default"])

        card = ctk.CTkFrame(self.list_frame, fg_color=cc["bg"], corner_radius=10)
        card.pack(fill="x", pady=3, padx=2)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)

        if cc["strip"]:
            ctk.CTkFrame(card, width=4, fg_color=cc["strip"],
                          corner_radius=2).place(x=3, y=6, relheight=0.7)

        emoji = cat_emoji(entry.get("category", ""))
        ctk.CTkLabel(inner, text=f"{emoji}  {entry.get('title', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                      text_color=TEXT_PRI, anchor="w").pack(fill="x")

        if entry.get("username"):
            ctk.CTkLabel(inner, text=entry.get("username", ""),
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEXT_SEC, anchor="w").pack(fill="x", pady=(1, 4))
        else:
            ctk.CTkFrame(inner, height=4, fg_color="transparent").pack()

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        cp_user = ctk.CTkButton(
            btn_row, text="📋 User", height=24, width=80,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6, text_color=TEXT_PRI,
            command=lambda: self._mini_copy(entry.get("username", ""), cp_user))
        cp_user.pack(side="left", padx=(0, 4))
        tip(cp_user, "Copy username to clipboard")

        cp_pass = ctk.CTkButton(
            btn_row, text="🔑 Pass", height=24, width=80,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=6, text_color="white",
            command=lambda: self._mini_copy(entry.get("password", ""), cp_pass))
        cp_pass.pack(side="left", padx=(0, 4))
        tip(cp_pass, "Copy password to clipboard")

        edit_btn = ctk.CTkButton(
            btn_row, text="✏️", height=24, width=36,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=6,
            text_color=TEXT_SEC,
            command=lambda: self._mini_edit(entry))
        edit_btn.pack(side="right")
        tip(edit_btn, "Edit this entry")

    def _mini_edit(self, entry):
        """Open the full vault's edit dialog for this entry."""
        self.app.restore_window()
        self.app.show_entry_dialog(entry)

    def _mini_copy(self, text, btn):
        pyperclip.copy(text)
        orig = btn.cget("text")
        orig_fg = btn.cget("fg_color")
        btn.configure(text="✅ Copied!", fg_color=GREEN)
        self.after(1000, lambda: self._safe_cfg(btn, orig, orig_fg))
        # Auto-clear clipboard via main app
        clear_sec = self.app.settings.get("clipboard_clear_seconds", 0)
        if clear_sec > 0:
            if self.app._clipboard_timer:
                self.app.root.after_cancel(self.app._clipboard_timer)
            self.app._clipboard_timer = self.app.root.after(
                clear_sec * 1000, self.app._clear_clipboard)

    @staticmethod
    def _safe_cfg(btn, t, fg):
        try:
            btn.configure(text=t, fg_color=fg)
        except Exception:
            pass


# ─── Floating Widget ─────────────────────────────────────────
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
        self.canvas.create_text(28, 28, text="🔐", font=("Segoe UI Emoji", 22))

        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Button-3>", self.show_menu)
        self._drag_data = {"x": 0, "y": 0, "moved": False}

    def start_drag(self, e):
        self._drag_data.update(x=e.x, y=e.y, moved=False)

    def do_drag(self, e):
        if abs(e.x - self._drag_data["x"]) > 2 or abs(e.y - self._drag_data["y"]) > 2:
            self._drag_data["moved"] = True
        self.geometry(f"+{self.winfo_x() - self._drag_data['x'] + e.x}+"
                      f"{self.winfo_y() - self._drag_data['y'] + e.y}")

    def stop_drag(self, e):
        if not self._drag_data["moved"]:
            self.app.toggle_mini_vault()

    def show_menu(self, e):
        menu = tk.Menu(self, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 10))
        menu.add_command(label="⬜  Open Full Vault", command=self.app.restore_window)
        menu.add_command(label="📋  Mini Vault", command=self.app.toggle_mini_vault)
        menu.add_separator()
        menu.add_command(label="✕  Exit", command=self.app.quit_app)
        menu.post(e.x_root, e.y_root)


# ═══════════════════════════════════════════════════════════════
class PasswordVault:
    def __init__(self):
        self.key = None
        self.data = None
        self.floating_widget = None
        self.mini_vault = None
        self.current_category = "All"
        self._login_attempts = 0
        self._lockout_until = 0
        self._idle_timer = None
        self._main_frame = None
        self._clipboard_timer = None

        # Load persistent settings
        self.settings = load_settings()

        ctk.set_appearance_mode("dark")

        self.root = ctk.CTk()
        self.root.title("Password Vault")
        self.root.geometry("880x600")
        self.root.minsize(720, 520)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_widget)

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 440
        y = (self.root.winfo_screenheight() // 2) - 300
        self.root.geometry(f"880x600+{x}+{y}")

        try:
            icon_path = os.path.join(APP_DIR, "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.show_login()

    # ─── Auto-Lock ───────────────────────────────────────────
    def _start_idle_timer(self):
        self._bind_activity_events()
        self._reset_idle()

    def _bind_activity_events(self):
        for ev in ("<Motion>", "<Key>", "<Button>", "<MouseWheel>"):
            self.root.bind(ev, self._reset_idle, add="+")

    def _unbind_activity_events(self):
        for ev in ("<Motion>", "<Key>", "<Button>", "<MouseWheel>"):
            self.root.unbind(ev)

    def _reset_idle(self, event=None):
        if self._idle_timer:
            self.root.after_cancel(self._idle_timer)
        mins = self.settings.get("auto_lock_minutes", AUTO_LOCK_MINUTES)
        if mins > 0:
            self._idle_timer = self.root.after(mins * 60 * 1000, self._auto_lock)

    def _auto_lock(self):
        self.key = None
        self.data = None
        self._idle_timer = None
        self._unbind_activity_events()
        if self.mini_vault:
            try:
                self.mini_vault.destroy()
            except Exception:
                pass
            self.mini_vault = None
        if self._main_frame and self._main_frame.winfo_exists():
            self._main_frame.destroy()
            self._main_frame = None
        self.show_login()

    # ─── Login Screen ────────────────────────────────────────
    def show_login(self):
        self.login_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.login_frame.place(relx=0.5, rely=0.45, anchor="center")

        circle = ctk.CTkFrame(self.login_frame, width=90, height=90,
                                corner_radius=45, fg_color=ACCENT)
        circle.pack(pady=(0, 18))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="🔐", font=ctk.CTkFont(size=40),
                      fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.login_frame, text="Password Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 4))

        is_new = not os.path.exists(DATA_FILE)
        ctk.CTkLabel(self.login_frame,
                      text="Create a master password" if is_new else "Enter your master password",
                      font=ctk.CTkFont(family="Segoe UI", size=13),
                      text_color=TEXT_SEC).pack(pady=(0, 24))

        pw_frame = ctk.CTkFrame(self.login_frame, fg_color="transparent")
        pw_frame.pack(pady=(0, 6))

        self.master_entry = ctk.CTkEntry(
            pw_frame, width=280, height=44,
            placeholder_text="Master Password",
            show="●", font=ctk.CTkFont(family="Segoe UI", size=14), justify="center",
            fg_color=BG_SEC, border_color=BG_TERT, border_width=1,
            corner_radius=12, text_color=TEXT_PRI)
        self.master_entry.pack(side="left")
        self.master_entry.bind("<Return>", lambda e: self.unlock())
        tip(self.master_entry, "Enter your master password to unlock the vault")

        def toggle_master():
            if self.master_entry.cget("show") == "●":
                self.master_entry.configure(show="")
                eye_master.configure(text="🙈")
            else:
                self.master_entry.configure(show="●")
                eye_master.configure(text="👁")

        eye_master = ctk.CTkButton(
            pw_frame, text="👁", width=36, height=44,
            font=ctk.CTkFont(size=14), fg_color=BG_SEC,
            hover_color=BG_TERT, corner_radius=12,
            text_color=TEXT_SEC, command=toggle_master)
        eye_master.pack(side="left", padx=(4, 0))
        tip(eye_master, "Show / hide password")

        self.error_label = ctk.CTkLabel(self.login_frame, text="", text_color=RED,
                                         font=ctk.CTkFont(family="Segoe UI", size=12))
        self.error_label.pack(pady=(0, 2))

        self.confirm_entry = None
        if is_new:
            sf = ctk.CTkFrame(self.login_frame, fg_color="transparent")
            sf.pack(fill="x", pady=(0, 6))
            self.strength_bar = ctk.CTkProgressBar(
                sf, width=320, height=5, corner_radius=3,
                fg_color=BG_TERT, progress_color=TEXT_QUAT)
            self.strength_bar.pack(side="left")
            self.strength_bar.set(0)
            self.strength_label = ctk.CTkLabel(
                sf, text="", font=ctk.CTkFont(size=10), text_color=TEXT_QUAT)
            self.strength_label.pack(side="left", padx=(8, 0))
            self.master_entry.bind("<KeyRelease>", self._update_login_strength)
            tip(self.strength_bar, "Shows how strong your password is")

            self.confirm_entry = ctk.CTkEntry(
                self.login_frame, width=320, height=44,
                placeholder_text="Confirm Password",
                show="●", font=ctk.CTkFont(family="Segoe UI", size=14), justify="center",
                fg_color=BG_SEC, border_color=BG_TERT, border_width=1,
                corner_radius=12, text_color=TEXT_PRI)
            self.confirm_entry.pack(pady=(0, 10))
            self.confirm_entry.bind("<Return>", lambda e: self.unlock())
            tip(self.confirm_entry, "Re-enter your password to confirm")

        unlock_btn = ctk.CTkButton(
            self.login_frame,
            text="Unlock  🔓" if not is_new else "Create Vault  🔐",
            width=320, height=46,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=12,
            command=self.unlock)
        unlock_btn.pack(pady=(10, 0))
        tip(unlock_btn,
            "Decrypt and open your vault" if not is_new else "Create a new encrypted vault")

        self.master_entry.focus()

    def _update_login_strength(self, event=None):
        s, lbl, c = password_strength(self.master_entry.get())
        self.strength_bar.set(s / 4)
        self.strength_bar.configure(progress_color=c)
        self.strength_label.configure(text=lbl, text_color=c)

    def _validate_master_password(self, pw):
        if len(pw) < 8:
            return "⚠️ Too short (min 8 chars)"
        if not any(c.isupper() for c in pw):
            return "⚠️ Need at least one uppercase letter"
        if not any(c.islower() for c in pw):
            return "⚠️ Need at least one lowercase letter"
        if not any(c.isdigit() for c in pw):
            return "⚠️ Need at least one digit"
        return None

    def unlock(self):
        now = time.time()
        if now < self._lockout_until:
            remaining = int(self._lockout_until - now)
            self.error_label.configure(
                text=f"⚠️ Too many attempts. Wait {remaining}s")
            return
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
            err = self._validate_master_password(pw)
            if err:
                self.error_label.configure(text=err)
                return

        salt = get_or_create_salt()
        self.key = derive_key(pw, salt)
        max_att = self.settings.get("max_login_attempts", MAX_LOGIN_ATTEMPTS)
        lock_sec = self.settings.get("lockout_seconds", LOCKOUT_SECONDS)
        try:
            self.data = load_data(self.key)
        except Exception:
            self._login_attempts += 1
            rem = max_att - self._login_attempts
            if self._login_attempts >= max_att:
                self._lockout_until = time.time() + lock_sec
                self.error_label.configure(
                    text=f"⚠️ Locked for {lock_sec}s")
                self._login_attempts = 0
            else:
                self.error_label.configure(
                    text=f"⚠️ Wrong password ({rem} attempts left)")
            return

        self._login_attempts = 0
        if is_new:
            save_data(self.data, self.key)
        self.login_frame.destroy()
        self.build_ui()
        self._start_idle_timer()

    # ─── Main UI ─────────────────────────────────────────────
    def build_ui(self):
        self._main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self._main_frame.pack(fill="both", expand=True)

        # Top Bar
        top = ctk.CTkFrame(self._main_frame, height=52, fg_color=BG_SEC,
                            corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="🔐", font=ctk.CTkFont(size=20)).pack(
            side="left", padx=(16, 6))
        ctk.CTkLabel(top, text="Password Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                      text_color=TEXT_PRI).pack(side="left")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_entries())

        search_bar = make_search_bar(
            top, self.search_var,
            lambda: self.data.get("categories", []) if self.data else [],
            self._search_cat_filter,
            height=32, width=260)
        search_bar.pack(side="left", padx=16)

        # Settings
        settings_btn = ctk.CTkButton(
            top, text="⚙", width=32, height=32, font=ctk.CTkFont(size=15),
            fg_color="transparent", hover_color=BG_TERT, corner_radius=8,
            text_color=TEXT_SEC, command=self.show_settings_menu)
        settings_btn.pack(side="right", padx=(0, 10))
        tip(settings_btn, "Settings — Preferences, change password, lock vault")

        add_btn = ctk.CTkButton(
            top, text="＋  Add New", width=110, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
            command=lambda: self.show_entry_dialog())
        add_btn.pack(side="right", padx=(0, 6))
        tip(add_btn, "Add a new password entry")

        # Content
        content = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = ctk.CTkFrame(content, width=200, fg_color=SIDEBAR_BG,
                                      corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="Categories",
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_SEC).pack(pady=(16, 8), padx=16, anchor="w")

        self.cat_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=SIDEBAR_BG)
        self.cat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        add_cat_btn = ctk.CTkButton(
            self.sidebar, text="＋  Category", height=30,
            font=ctk.CTkFont(family="Segoe UI", size=11), fg_color="transparent",
            border_width=1, border_color=TEXT_QUAT, corner_radius=8,
            hover_color=BG_TERT, text_color=TEXT_SEC,
            command=self.show_add_cat_dialog)
        add_cat_btn.pack(pady=(0, 10), padx=12, fill="x")
        tip(add_cat_btn, "Create a new category to organize passwords")

        # Entries
        self.entries_panel = ctk.CTkScrollableFrame(
            content, fg_color=BG, corner_radius=0,
            scrollbar_button_color=BG_SEC)
        self.entries_panel.pack(side="right", fill="both", expand=True)

        self.refresh_categories()
        self.refresh_entries()

    def _search_cat_filter(self, cat):
        self.current_category = cat
        self.refresh_categories()
        self.refresh_entries()

    # ─── Settings Menu ───────────────────────────────────────
    def show_settings_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 10))
        menu.add_command(label="⚙️  Settings",
                          command=self.show_settings_dialog)
        menu.add_command(label="🔑  Change Master Password",
                          command=self.show_change_password_dialog)
        menu.add_separator()
        menu.add_command(label="🔒  Lock Vault", command=self._auto_lock)
        menu.add_separator()
        menu.add_command(label="ℹ️  About", command=self.show_about_dialog)
        try:
            menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except Exception:
            pass

    # ─── About Dialog ────────────────────────────────────────
    def show_about_dialog(self):
        self._reset_idle()
        DW, DH = 380, 420
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("About Password Vault")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        # Icon
        circle = ctk.CTkFrame(dlg, width=80, height=80,
                                corner_radius=40, fg_color=ACCENT)
        circle.pack(pady=(24, 10))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="🔐", font=ctk.CTkFont(size=36),
                      fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")

        # App name
        ctk.CTkLabel(dlg, text="Password Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 2))

        # Version badge
        ver_frame = ctk.CTkFrame(dlg, fg_color=ACCENT, corner_radius=12)
        ver_frame.pack(pady=(0, 14))
        ctk.CTkLabel(ver_frame, text=f"  v{APP_VERSION}  ",
                      font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                      text_color="white").pack(padx=8, pady=2)

        # Info group
        g = ios_group(dlg, "Information")

        def info_row(grp, icon, label, value, idx=0):
            if idx > 0:
                ctk.CTkFrame(grp, height=1, fg_color=SEPARATOR).pack(
                    fill="x", padx=(46, 0))
            row = ctk.CTkFrame(grp, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(row, text=f"{icon}  {label}",
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          text_color=TEXT_SEC, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value,
                          font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                          text_color=TEXT_PRI, anchor="e").pack(side="right")

        info_row(g, "📦", "Version", f"v{APP_VERSION}", idx=0)
        info_row(g, "👨‍💻", "Developer", APP_AUTHOR, idx=1)
        info_row(g, "🛡️", "Encryption", "AES-256 (Fernet)", idx=2)
        info_row(g, "🔑", "Key Derivation", "PBKDF2-SHA256", idx=3)
        info_row(g, "📂", "Data Location", "%APPDATA%", idx=4)

        # Features summary
        g2 = ios_group(dlg, "Features")
        features = [
            "🔐  AES-256 encrypted local vault",
            "🎲  Secure password generator",
            "🔒  Auto-lock & brute-force protection",
            "📋  Quick-copy with auto-clear clipboard",
            "🎨  Custom card colors & categories",
            "📌  Floating widget & Mini Vault",
            "⚙️  Customizable settings",
        ]
        for i, feat in enumerate(features):
            if i > 0:
                ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
                    fill="x", padx=(16, 0))
            ctk.CTkLabel(g2, text=feat,
                          font=ctk.CTkFont(family="Segoe UI", size=11),
                          text_color=TEXT_PRI, anchor="w").pack(
                fill="x", padx=12, pady=3)

        # Close button
        ctk.CTkButton(
            dlg, text="Close", height=36, width=140,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=BG_TERT, hover_color=CARD_HOVER, corner_radius=10,
            command=dlg.destroy).pack(pady=(14, 16))

    # ─── Settings Dialog (Full Page, iOS Style) ──────────────
    def show_settings_dialog(self):
        self._reset_idle()
        DW, DH = 480, 620
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Settings")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        ctk.CTkLabel(dlg, text="⚙️  Settings",
                      font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                         scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        s = dict(self.settings)  # working copy

        # ── helper to create a setting row ──
        def setting_row(group, icon, label, idx=0):
            if idx > 0:
                ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
                    fill="x", padx=(46, 0))
            row = ctk.CTkFrame(group, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=5)
            lbl_w = ctk.CTkLabel(row, text=f"{icon}  {label}",
                                   font=ctk.CTkFont(family="Segoe UI", size=12),
                                   text_color=TEXT_PRI, anchor="w")
            lbl_w.pack(side="left", fill="x", expand=True)
            return row, lbl_w

        # ════════════════ SECURITY ════════════════
        g_sec = ios_group(scroll, "Security")

        # — Auto-Lock Timer —
        r, lbl = setting_row(g_sec, "🔒", "Auto-Lock", idx=0)
        al_map = {"1 min": 1, "2 min": 2, "5 min": 5,
                  "10 min": 10, "15 min": 15, "30 min": 30, "Never": 0}
        al_rev = {v: k for k, v in al_map.items()}
        al_var = ctk.StringVar(value=al_rev.get(s["auto_lock_minutes"], "5 min"))
        al_opt = ctk.CTkOptionMenu(
            r, values=list(al_map.keys()), variable=al_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        al_opt.pack(side="right")
        tip(lbl, "Lock the vault automatically after this period of inactivity. "
                 "'Never' disables auto-lock.")
        tip(al_opt, "Choose auto-lock duration")

        # — Max Login Attempts —
        r2, lbl2 = setting_row(g_sec, "🛡️", "Max Login Attempts", idx=1)
        att_map = {"3": 3, "5": 5, "10": 10, "15": 15}
        att_var = ctk.StringVar(value=str(s["max_login_attempts"]))
        att_opt = ctk.CTkOptionMenu(
            r2, values=list(att_map.keys()), variable=att_var,
            width=80, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        att_opt.pack(side="right")
        tip(lbl2, "Maximum wrong password attempts before a temporary lockout.")
        tip(att_opt, "Choose max attempts")

        # — Lockout Duration —
        r3, lbl3 = setting_row(g_sec, "⏱️", "Lockout Duration", idx=2)
        lo_map = {"15 sec": 15, "30 sec": 30, "60 sec": 60,
                  "2 min": 120, "5 min": 300}
        lo_rev = {v: k for k, v in lo_map.items()}
        lo_var = ctk.StringVar(value=lo_rev.get(s["lockout_seconds"], "30 sec"))
        lo_opt = ctk.CTkOptionMenu(
            r3, values=list(lo_map.keys()), variable=lo_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        lo_opt.pack(side="right")
        tip(lbl3, "How long the vault stays locked after too many failed attempts.")
        tip(lo_opt, "Choose lockout duration")

        # — Clear Clipboard —
        r4, lbl4 = setting_row(g_sec, "📋", "Clear Clipboard", idx=3)
        cl_map = {"Off": 0, "10 sec": 10, "15 sec": 15, "30 sec": 30, "60 sec": 60}
        cl_rev = {v: k for k, v in cl_map.items()}
        cl_var = ctk.StringVar(value=cl_rev.get(s["clipboard_clear_seconds"], "Off"))
        cl_opt = ctk.CTkOptionMenu(
            r4, values=list(cl_map.keys()), variable=cl_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        cl_opt.pack(side="right")
        tip(lbl4, "Automatically clear copied passwords from clipboard after this time.")
        tip(cl_opt, "Choose clipboard clear delay")

        # ════════════════ PASSWORD GENERATOR ════════════════
        g_gen = ios_group(scroll, "Password Generator Defaults")

        # — Default Length —
        r5, lbl5 = setting_row(g_gen, "📏", "Default Length", idx=0)
        gl_var = ctk.IntVar(value=s.get("gen_length", 16))
        gl_lbl = ctk.CTkLabel(r5, text=str(gl_var.get()),
                                font=ctk.CTkFont(size=11, weight="bold"),
                                text_color=TEXT_PRI, width=28)
        gl_lbl.pack(side="right")

        def on_gl(v):
            gl_var.set(int(float(v)))
            gl_lbl.configure(text=str(int(float(v))))

        gl_slider = ctk.CTkSlider(
            r5, from_=6, to=40, number_of_steps=34, command=on_gl,
            width=140, fg_color=BG_TERT, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER)
        gl_slider.set(gl_var.get())
        gl_slider.pack(side="right", padx=(0, 8))
        tip(lbl5, "Default password length when opening the generator.")
        tip(gl_slider, "Drag to set default password length (6–40)")

        # — Character types —
        r6, lbl6 = setting_row(g_gen, "🔤", "Uppercase (ABC)", idx=1)
        gen_upper = ctk.CTkSwitch(r6, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_upper.pack(side="right")
        if s.get("gen_upper", True):
            gen_upper.select()
        tip(lbl6, "Include uppercase letters (A-Z) in generated passwords.")

        r7, lbl7 = setting_row(g_gen, "🔡", "Lowercase (abc)", idx=2)
        gen_lower = ctk.CTkSwitch(r7, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_lower.pack(side="right")
        if s.get("gen_lower", True):
            gen_lower.select()
        tip(lbl7, "Include lowercase letters (a-z) in generated passwords.")

        r8, lbl8 = setting_row(g_gen, "🔢", "Digits (0-9)", idx=3)
        gen_digits = ctk.CTkSwitch(r8, text="", width=46,
                                     fg_color=BG_TERT, progress_color=GREEN,
                                     button_color=TEXT_PRI)
        gen_digits.pack(side="right")
        if s.get("gen_digits", True):
            gen_digits.select()
        tip(lbl8, "Include digits (0-9) in generated passwords.")

        r9, lbl9 = setting_row(g_gen, "🔣", "Symbols (#$%&)", idx=4)
        gen_symbols = ctk.CTkSwitch(r9, text="", width=46,
                                      fg_color=BG_TERT, progress_color=GREEN,
                                      button_color=TEXT_PRI)
        gen_symbols.pack(side="right")
        if s.get("gen_symbols", True):
            gen_symbols.select()
        tip(lbl9, "Include special symbols (!@#$%&) in generated passwords.")

        # ════════════════ APPEARANCE ════════════════
        g_app = ios_group(scroll, "Appearance")

        # — Default Card Color —
        r10, lbl10 = setting_row(g_app, "🎨", "Default Card Color", idx=0)
        tip(lbl10, "Default color for new password entries.")

        def_color_var = ctk.StringVar(value=s.get("default_card_color", "default"))
        color_btns = {}
        color_row = ctk.CTkFrame(g_app, fg_color="transparent")
        color_row.pack(fill="x", padx=12, pady=(0, 6))

        for ckey, info in CARD_COLORS.items():
            btn_color = info["strip"] if info["strip"] else BG_TERT
            is_sel = def_color_var.get() == ckey
            b = ctk.CTkButton(
                color_row, text="✓" if is_sel else "",
                width=28, height=28, fg_color=btn_color,
                hover_color=btn_color, corner_radius=14,
                font=ctk.CTkFont(size=12, weight="bold"), text_color="white",
                command=lambda k=ckey: _sel_def_color(k))
            b.pack(side="left", padx=3)
            color_btns[ckey] = b
            tip(b, f"{info['label']} — set as default card color")

        def _sel_def_color(k):
            def_color_var.set(k)
            for ck, cb in color_btns.items():
                cb.configure(text="✓" if ck == k else "")

        # ════════════════ BEHAVIOR ════════════════
        g_beh = ios_group(scroll, "Behavior")

        r11, lbl11 = setting_row(g_beh, "🚀", "Start Minimized", idx=0)
        start_min = ctk.CTkSwitch(r11, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        start_min.pack(side="right")
        if s.get("start_minimized", False):
            start_min.select()
        tip(lbl11, "Start the app minimized to the floating widget instead of "
                   "showing the full window.")

        # ════════════════ SAVE BUTTON ════════════════
        def apply_settings():
            self.settings["auto_lock_minutes"] = al_map.get(al_var.get(), 5)
            self.settings["max_login_attempts"] = int(att_var.get())
            self.settings["lockout_seconds"] = lo_map.get(lo_var.get(), 30)
            self.settings["clipboard_clear_seconds"] = cl_map.get(cl_var.get(), 0)
            self.settings["gen_length"] = gl_var.get()
            self.settings["gen_upper"] = bool(gen_upper.get())
            self.settings["gen_lower"] = bool(gen_lower.get())
            self.settings["gen_digits"] = bool(gen_digits.get())
            self.settings["gen_symbols"] = bool(gen_symbols.get())
            self.settings["default_card_color"] = def_color_var.get()
            self.settings["start_minimized"] = bool(start_min.get())
            save_settings(self.settings)
            # Re-arm the idle timer with new value
            self._reset_idle()
            dlg.destroy()

        bottom = ctk.CTkFrame(dlg, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 12))

        save_btn = ctk.CTkButton(
            bottom, text="💾  Save Settings", height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=apply_settings)
        save_btn.pack(fill="x")
        tip(save_btn, "Save all settings and close")

    # ─── Change Master Password ──────────────────────────────
    def show_change_password_dialog(self):
        self._reset_idle()
        DW, DH = 400, 380
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Change Master Password")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        ctk.CTkLabel(dlg, text="🔑", font=ctk.CTkFont(size=32)).pack(pady=(16, 2))
        ctk.CTkLabel(dlg, text="Change Master Password",
                      font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 10))

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        g1 = ios_group(frm, "Current")
        old_e = ios_field(g1, "Password", idx=0, show="●")

        g2 = ios_group(frm, "New Password")
        new_e = ios_field(g2, "Password", idx=0, show="●")

        sf = ctk.CTkFrame(frm, fg_color="transparent")
        sf.pack(fill="x", padx=14, pady=(0, 4))
        sb = ctk.CTkProgressBar(sf, height=4, corner_radius=2,
                                  fg_color=BG_TERT, progress_color=TEXT_QUAT)
        sb.pack(side="left", fill="x", expand=True)
        sb.set(0)
        sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                            text_color=TEXT_QUAT)
        sl.pack(side="left", padx=(6, 0))

        def upd(e=None):
            s, lbl, c = password_strength(new_e.get())
            sb.set(s / 4)
            sb.configure(progress_color=c)
            sl.configure(text=lbl, text_color=c)

        new_e.bind("<KeyRelease>", upd)

        g3 = ios_group(frm, "Confirm")
        conf_e = ios_field(g3, "Password", idx=0, show="●")

        err = ctk.CTkLabel(frm, text="", text_color=RED,
                            font=ctk.CTkFont(size=11))
        err.pack(pady=(2, 4))

        def save():
            op = old_e.get()
            np_ = new_e.get()
            cp = conf_e.get()
            if not op or not np_:
                err.configure(text="⚠️ Fill all fields")
                return
            salt = get_or_create_salt()
            if derive_key(op, salt) != self.key:
                err.configure(text="⚠️ Current password is wrong")
                return
            if np_ != cp:
                err.configure(text="⚠️ New passwords don't match")
                return
            ve = self._validate_master_password(np_)
            if ve:
                err.configure(text=ve)
                return
            self.key = derive_key(np_, salt)
            save_data(self.data, self.key)
            dlg.destroy()

        save_btn = ctk.CTkButton(
            frm, text="Change Password", height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ORANGE, hover_color=ORANGE_HOVER, corner_radius=10,
            command=save)
        save_btn.pack(fill="x", padx=14)
        tip(save_btn, "Save the new master password")
        old_e.focus()

    # ─── Categories ──────────────────────────────────────────
    def refresh_categories(self):
        for w in self.cat_frame.winfo_children():
            w.destroy()
        cats = ["All"] + self.data.get("categories", [])
        for cat in cats:
            if cat == "All":
                count = len(self.data["entries"])
            else:
                count = sum(1 for e in self.data["entries"]
                            if e.get("category") == cat)
            emoji = "🗂️" if cat == "All" else cat_emoji(cat)
            active = cat == self.current_category

            row = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            btn = ctk.CTkButton(
                row, text=f" {emoji}  {cat}   ({count})",
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                  weight="bold" if active else "normal"),
                fg_color=SIDEBAR_SEL if active else "transparent",
                hover_color=ACCENT_HOVER if active else BG_TERT,
                text_color="white" if active else TEXT_PRI,
                anchor="w", height=34, corner_radius=8,
                command=lambda c=cat: self.select_cat(c))
            btn.pack(side="left", fill="x", expand=True)
            tip(btn, f"Show {'all entries' if cat == 'All' else f'entries in {cat}'}")

            if cat != "All":
                del_btn = ctk.CTkButton(
                    row, text="✕", width=26, height=26,
                    font=ctk.CTkFont(size=10), fg_color="transparent",
                    hover_color=RED_HOVER, corner_radius=6, text_color=TEXT_TERT,
                    command=lambda c=cat: self.confirm_delete_category(c))
                del_btn.pack(side="right", padx=(2, 0))
                tip(del_btn, f"Delete '{cat}' category")

    def select_cat(self, cat):
        self.current_category = cat
        self.refresh_categories()
        self.refresh_entries()

    # ─── Delete Category ─────────────────────────────────────
    def confirm_delete_category(self, cat_name):
        self._reset_idle()
        n = sum(1 for e in self.data["entries"]
                if e.get("category") == cat_name)
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Delete Category")
        dlg.geometry("380x190")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, 380, 190)

        ctk.CTkLabel(dlg, text="⚠️  Delete Category?",
                      font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(20, 4))
        msg = f'Delete "{cat_name}"?'
        if n > 0:
            msg += f'\n{n} entries → "General".'
        ctk.CTkLabel(dlg, text=msg, font=ctk.CTkFont(size=12),
                      text_color=TEXT_SEC, justify="center").pack(pady=(0, 14))

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=24)

        def do_del():
            for e in self.data["entries"]:
                if e.get("category") == cat_name:
                    e["category"] = "General"
            self.data["categories"].remove(cat_name)
            if "General" not in self.data["categories"]:
                self.data["categories"].insert(0, "General")
            save_data(self.data, self.key)
            dlg.destroy()
            if self.current_category == cat_name:
                self.current_category = "All"
            self.refresh_categories()
            self.refresh_entries()

        ctk.CTkButton(
            bf, text="Delete", fg_color=RED, hover_color=RED_HOVER,
            width=140, height=36, font=ctk.CTkFont(size=13), corner_radius=10,
            command=do_del).pack(side="left", padx=4)
        ctk.CTkButton(
            bf, text="Cancel", fg_color=BG_TERT, hover_color=CARD_HOVER,
            width=140, height=36, font=ctk.CTkFont(size=13), corner_radius=10,
            command=dlg.destroy).pack(side="right", padx=4)

    # ─── Entries ─────────────────────────────────────────────
    def refresh_entries(self):
        for w in self.entries_panel.winfo_children():
            w.destroy()
        search = ""
        if hasattr(self, "search_var"):
            search = self.search_var.get().lower()
        entries = list(self.data["entries"])
        if self.current_category != "All":
            entries = [e for e in entries
                       if e.get("category") == self.current_category]
        if search:
            entries = [e for e in entries
                       if search in e.get("title", "").lower()
                       or search in e.get("username", "").lower()
                       or search in e.get("category", "").lower()]
        if not entries:
            ef = ctk.CTkFrame(self.entries_panel, fg_color="transparent")
            ef.pack(expand=True, fill="both")
            ctk.CTkLabel(ef, text="📭", font=ctk.CTkFont(size=48)).pack(
                pady=(80, 8))
            ctk.CTkLabel(ef, text="No passwords yet",
                          font=ctk.CTkFont(family="Segoe UI", size=15),
                          text_color=TEXT_TERT).pack()
            ctk.CTkLabel(ef, text="Click '＋ Add New' to get started",
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          text_color=TEXT_QUAT).pack(pady=(4, 0))
            return
        for entry in entries:
            self._card(entry)

    def _card(self, entry):
        color_key = entry.get("color", "default")
        cc = CARD_COLORS.get(color_key, CARD_COLORS["default"])

        card = ctk.CTkFrame(self.entries_panel, fg_color=cc["bg"],
                              corner_radius=10)
        card.pack(fill="x", pady=2, padx=8)

        if cc["strip"]:
            ctk.CTkFrame(card, width=3, fg_color=cc["strip"],
                          corner_radius=2).place(x=3, y=6, relheight=0.78)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=(14 if cc["strip"] else 12), pady=6)

        # Row 1: Title + badge + actions
        r1 = ctk.CTkFrame(inner, fg_color="transparent")
        r1.pack(fill="x", pady=(0, 2))
        emoji = cat_emoji(entry.get("category", ""))
        ctk.CTkLabel(r1, text=f"{emoji}  {entry.get('title', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                      text_color=TEXT_PRI).pack(side="left")
        ctk.CTkLabel(r1, text=f" {entry.get('category', '')} ",
                      font=ctk.CTkFont(family="Segoe UI", size=9),
                      text_color=TEXT_SEC, fg_color=BADGE_BG,
                      corner_radius=4).pack(side="left", padx=(8, 0))

        del_btn = ctk.CTkButton(
            r1, text="🗑", width=24, height=24, fg_color="transparent",
            hover_color=RED_HOVER, corner_radius=5, font=ctk.CTkFont(size=11),
            command=lambda: self.confirm_delete(entry))
        del_btn.pack(side="right", padx=1)
        tip(del_btn, "Delete this entry")

        edit_btn = ctk.CTkButton(
            r1, text="✏", width=24, height=24, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5, font=ctk.CTkFont(size=11),
            command=lambda: self.show_entry_dialog(entry))
        edit_btn.pack(side="right", padx=1)
        tip(edit_btn, "Edit this entry")

        # Row 2: User + Pass (compact single row)
        r2 = ctk.CTkFrame(inner, fg_color="transparent")
        r2.pack(fill="x", pady=(0, 1))
        ctk.CTkLabel(r2, text=f"👤 {entry.get('username', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_SEC, anchor="w").pack(side="left")
        cu = ctk.CTkButton(
            r2, text="📋", width=28, height=22, font=ctk.CTkFont(size=10),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=5,
            command=lambda: self._copy(entry.get("username", ""), cu))
        cu.pack(side="left", padx=(6, 0))
        tip(cu, "Copy username")

        pwd = entry.get("password", "")
        cp = ctk.CTkButton(
            r2, text="🔑 Copy", width=65, height=22, font=ctk.CTkFont(size=10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            corner_radius=5,
            command=lambda: self._copy(pwd, cp))
        cp.pack(side="right")
        tip(cp, "Copy password")

        plbl = ctk.CTkLabel(r2, text="●" * min(len(pwd), 12),
                              font=ctk.CTkFont(size=11),
                              text_color=TEXT_TERT, anchor="e")
        plbl.pack(side="right", padx=(0, 4))

        def toggle(lbl=plbl, real=pwd):
            if "●" in lbl.cget("text"):
                lbl.configure(text=real[:20])
                eye.configure(text="🙈")
            else:
                lbl.configure(text="●" * min(len(real), 12))
                eye.configure(text="👁")

        eye = ctk.CTkButton(
            r2, text="👁", width=24, height=22, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5, font=ctk.CTkFont(size=10),
            command=toggle)
        eye.pack(side="right", padx=(0, 2))
        tip(eye, "Show / hide password")

        # Notes (compact)
        notes = entry.get("notes", "")
        if notes:
            ctk.CTkLabel(inner, text=notes,
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEXT_TERT, anchor="w", wraplength=400,
                          justify="left").pack(fill="x", pady=(2, 0))

    def _copy(self, text, btn):
        pyperclip.copy(text)
        orig = btn.cget("text")
        orig_fg = btn.cget("fg_color")
        btn.configure(text="✅ Done!", fg_color=GREEN)
        self.root.after(1000, lambda: self._safe_cfg(btn, orig, orig_fg))
        # Auto-clear clipboard
        clear_sec = self.settings.get("clipboard_clear_seconds", 0)
        if clear_sec > 0:
            if self._clipboard_timer:
                self.root.after_cancel(self._clipboard_timer)
            self._clipboard_timer = self.root.after(
                clear_sec * 1000, self._clear_clipboard)

    def _clear_clipboard(self):
        try:
            pyperclip.copy("")
        except Exception:
            pass
        self._clipboard_timer = None

    @staticmethod
    def _safe_cfg(btn, t, fg):
        try:
            btn.configure(text=t, fg_color=fg)
        except Exception:
            pass

    # ─── Password Generator ──────────────────────────────────
    def _show_generator(self, target_entry):
        self._reset_idle()
        DW, DH = 380, 330
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Password Generator")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        ctk.CTkLabel(dlg, text="🎲  Password Generator",
                      font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 8))

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        _gl = self.settings.get("gen_length", 16)
        gen_var = ctk.StringVar(value=generate_password(
            _gl,
            self.settings.get("gen_upper", True),
            self.settings.get("gen_lower", True),
            self.settings.get("gen_digits", True),
            self.settings.get("gen_symbols", True)))
        gen_entry = ctk.CTkEntry(
            frm, height=38,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            textvariable=gen_var, fg_color=BG_SEC, border_width=1,
            border_color=ACCENT, corner_radius=10, justify="center",
            text_color=TEXT_PRI)
        gen_entry.pack(fill="x", pady=(0, 5))
        tip(gen_entry, "Generated password — click Use This to apply it")

        sf = ctk.CTkFrame(frm, fg_color="transparent")
        sf.pack(fill="x", pady=(0, 8))
        sb = ctk.CTkProgressBar(sf, height=4, corner_radius=2,
                                  fg_color=BG_TERT, progress_color=GREEN)
        sb.pack(side="left", fill="x", expand=True)
        sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                            text_color=GREEN)
        sl.pack(side="left", padx=(6, 0))

        lv = ctk.IntVar(value=self.settings.get("gen_length", 16))
        uv = ctk.BooleanVar(value=self.settings.get("gen_upper", True))
        lov = ctk.BooleanVar(value=self.settings.get("gen_lower", True))
        dv = ctk.BooleanVar(value=self.settings.get("gen_digits", True))
        sv = ctk.BooleanVar(value=self.settings.get("gen_symbols", True))

        lf = ctk.CTkFrame(frm, fg_color="transparent")
        lf.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(lf, text="Length:", font=ctk.CTkFont(size=11),
                      text_color=TEXT_SEC).pack(side="left")
        ll = ctk.CTkLabel(lf, text=str(_gl),
                            font=ctk.CTkFont(size=11, weight="bold"),
                            text_color=TEXT_PRI, width=28)
        ll.pack(side="right")

        def regen(*_):
            pw = generate_password(lv.get(), uv.get(), lov.get(),
                                    dv.get(), sv.get())
            gen_var.set(pw)
            s, lbl, c = password_strength(pw)
            sb.set(s / 4)
            sb.configure(progress_color=c)
            sl.configure(text=lbl, text_color=c)

        def on_len(v):
            lv.set(int(v))
            ll.configure(text=str(int(v)))
            regen()

        slider = ctk.CTkSlider(
            lf, from_=6, to=40, number_of_steps=34, command=on_len,
            fg_color=BG_TERT, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER)
        slider.set(_gl)
        slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
        tip(slider, "Drag to change password length")

        cf = ctk.CTkFrame(frm, fg_color="transparent")
        cf.pack(fill="x", pady=(0, 8))
        for txt, var, desc in [("ABC", uv, "Include uppercase letters"),
                                ("abc", lov, "Include lowercase letters"),
                                ("123", dv, "Include digits"),
                                ("#$%", sv, "Include special characters")]:
            chk = ctk.CTkCheckBox(
                cf, text=txt, variable=var, font=ctk.CTkFont(size=11),
                fg_color=ACCENT, hover_color=ACCENT_HOVER, command=regen)
            chk.pack(side="left", padx=(0, 10))
            tip(chk, desc)

        bf = ctk.CTkFrame(frm, fg_color="transparent")
        bf.pack(fill="x")
        regen_btn = ctk.CTkButton(
            bf, text="🔄  Regenerate", height=32, font=ctk.CTkFont(size=12),
            fg_color=BG_TERT, hover_color=TEXT_QUAT, corner_radius=8,
            command=regen)
        regen_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tip(regen_btn, "Generate a new random password")

        def use():
            target_entry.delete(0, "end")
            target_entry.insert(0, gen_var.get())
            dlg.destroy()

        use_btn = ctk.CTkButton(
            bf, text="✅  Use This", height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=8, command=use)
        use_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
        tip(use_btn, "Apply this password to the entry")
        regen()

    # ─── Unified Add / Edit Dialog (Compact, iOS Style) ──────
    def show_entry_dialog(self, entry=None):
        self._reset_idle()
        is_edit = entry is not None
        DW, DH = 400, 500
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Edit Password" if is_edit else "New Password")
        dlg.geometry(f"{DW}x{DH}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, DW, DH)

        ctk.CTkLabel(
            dlg,
            text="✏️  Edit Password" if is_edit else "＋  New Password",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(8, 4))

        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=12, pady=(0, 0))

        # IDENTITY
        g1 = ios_group(frm, "Identity", compact=True)
        title_val = entry.get("title", "") if is_edit else ""
        title_e = ios_field(g1, "Title", idx=0, value=title_val, height=30)
        cats = self.data.get("categories", ["General"])
        cat_val = entry.get("category", cats[0] if cats else "") if is_edit else (cats[0] if cats else "")
        cat_cb = ios_combo(g1, "Category", cats, cat_val, idx=1)

        # CREDENTIALS
        g2 = ios_group(frm, "Credentials", compact=True)
        user_val = entry.get("username", "") if is_edit else ""
        user_e = ios_field(g2, "Username", idx=0, value=user_val, height=30)

        ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
        pw_row = ctk.CTkFrame(g2, fg_color="transparent")
        pw_row.pack(fill="x", padx=12, pady=(2, 3))
        ctk.CTkLabel(pw_row, text="Password",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, width=72, anchor="w").pack(side="left")
        pass_e = ctk.CTkEntry(
            pw_row, height=30, show="●",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=6,
            text_color=TEXT_PRI)
        pass_e.pack(side="left", fill="x", expand=True, padx=(4, 4))
        if is_edit:
            pass_e.insert(0, entry.get("password", ""))
        gen_btn = ctk.CTkButton(
            pw_row, text="🎲", width=28, height=28, font=ctk.CTkFont(size=13),
            fg_color=GREEN, hover_color=GREEN_HOVER, corner_radius=6,
            text_color=BG, command=lambda: self._show_generator(pass_e))
        gen_btn.pack(side="right")
        tip(gen_btn, "Open password generator")

        def toggle_pass():
            if pass_e.cget("show") == "●":
                pass_e.configure(show="")
                eye_btn.configure(text="🙈")
            else:
                pass_e.configure(show="●")
                eye_btn.configure(text="👁")

        eye_btn = ctk.CTkButton(
            pw_row, text="👁", width=28, height=28, font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=BG_TERT, corner_radius=6,
            text_color=TEXT_SEC, command=toggle_pass)
        eye_btn.pack(side="right", padx=(0, 2))
        tip(eye_btn, "Show / hide password")

        # Strength
        sf = ctk.CTkFrame(frm, fg_color="transparent")
        sf.pack(fill="x", padx=26, pady=(0, 2))
        str_bar = ctk.CTkProgressBar(
            sf, height=3, corner_radius=2,
            fg_color=BG_TERT, progress_color=TEXT_QUAT)
        str_bar.pack(side="left", fill="x", expand=True)
        str_bar.set(0)
        str_lbl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                                text_color=TEXT_QUAT)
        str_lbl.pack(side="left", padx=(6, 0))
        tip(str_bar, "Password strength indicator")

        def upd_str(e=None):
            s, lbl, c = password_strength(pass_e.get())
            str_bar.set(s / 4)
            str_bar.configure(progress_color=c)
            str_lbl.configure(text=lbl, text_color=c)

        pass_e.bind("<KeyRelease>", upd_str)
        if is_edit:
            upd_str()

        # COLOR picker
        g_color = ios_group(frm, "Color", compact=True)
        color_row = ctk.CTkFrame(g_color, fg_color="transparent")
        color_row.pack(fill="x", padx=10, pady=4)
        _def_color = self.settings.get("default_card_color", "default")
        current_color = ctk.StringVar(
            value=entry.get("color", "default") if is_edit else _def_color)

        color_btns = {}
        for ckey, info in CARD_COLORS.items():
            btn_color = info["strip"] if info["strip"] else BG_TERT
            is_selected = current_color.get() == ckey
            b = ctk.CTkButton(
                color_row, text="✓" if is_selected else "",
                width=24, height=24, fg_color=btn_color,
                hover_color=btn_color, corner_radius=12,
                font=ctk.CTkFont(size=11, weight="bold"), text_color="white",
                command=lambda k=ckey: _select_color(k))
            b.pack(side="left", padx=2)
            color_btns[ckey] = b
            tip(b, f"{info['label']} card color")

        def _select_color(k):
            current_color.set(k)
            for ck, cb in color_btns.items():
                cb.configure(text="✓" if ck == k else "")

        # NOTES
        g3 = ios_group(frm, "Notes", compact=True)
        notes_val = entry.get("notes", "") if is_edit else ""
        notes_tb = ios_field(g3, "Notes", idx=0, is_textbox=True,
                              height=32, value=notes_val)

        # Bottom
        bottom = ctk.CTkFrame(dlg, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 10))

        err = ctk.CTkLabel(bottom, text="", text_color=RED,
                            font=ctk.CTkFont(size=10), height=12)
        err.pack(pady=(0, 2))

        def save():
            t = title_e.get().strip()
            p = pass_e.get().strip()
            if not t:
                err.configure(text="⚠️ Title is required")
                return
            if not p:
                err.configure(text="⚠️ Password is required")
                return
            u = user_e.get().strip()
            c = cat_cb.get().strip()
            n = notes_tb.get("1.0", "end").strip()
            col = current_color.get()

            if is_edit:
                entry.update(title=t, username=u, password=p,
                              category=c, notes=n, color=col)
            else:
                self.data["entries"].append({
                    "id": str(uuid.uuid4()), "title": t, "username": u,
                    "password": p, "category": c, "notes": n, "color": col
                })
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        save_btn = ctk.CTkButton(
            bottom,
            text="💾  Save Changes" if is_edit else "💾  Save",
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=save)
        save_btn.pack(fill="x")
        tip(save_btn, "Save this password entry")
        title_e.focus()

    # ─── Delete Confirm ──────────────────────────────────────
    def confirm_delete(self, entry):
        self._reset_idle()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Delete")
        dlg.geometry("360x175")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, 360, 175)

        ctk.CTkLabel(dlg, text="⚠️  Are you sure?",
                      font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(20, 4))
        ctk.CTkLabel(dlg, text=f"Delete \"{entry.get('title', '')}\"?",
                      font=ctk.CTkFont(size=12),
                      text_color=TEXT_SEC).pack(pady=(0, 14))
        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=24)

        def do_del():
            eid = entry.get("id")
            if eid:
                self.data["entries"] = [
                    e for e in self.data["entries"]
                    if e.get("id") != eid
                ]
            else:
                try:
                    self.data["entries"].remove(entry)
                except ValueError:
                    pass
            save_data(self.data, self.key)
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        ctk.CTkButton(
            bf, text="Delete", fg_color=RED, hover_color=RED_HOVER,
            width=140, height=36, font=ctk.CTkFont(size=13), corner_radius=10,
            command=do_del).pack(side="left", padx=4)
        ctk.CTkButton(
            bf, text="Cancel", fg_color=BG_TERT, hover_color=CARD_HOVER,
            width=140, height=36, font=ctk.CTkFont(size=13), corner_radius=10,
            command=dlg.destroy).pack(side="right", padx=4)

    # ─── Add Category ────────────────────────────────────────
    def show_add_cat_dialog(self):
        self._reset_idle()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("New Category")
        dlg.geometry("350x185")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, 350, 185)

        ctk.CTkLabel(dlg, text="📁  New Category",
                      font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 10))
        frm = ctk.CTkFrame(dlg, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        g = ios_group(frm)
        cat_e = ios_field(g, "Name", idx=0, placeholder="Category name")
        cat_e.focus()
        err = ctk.CTkLabel(frm, text="", text_color=RED,
                            font=ctk.CTkFont(size=11))
        err.pack(pady=(2, 4))

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
        ctk.CTkButton(
            frm, text="＋  Add", height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=save).pack(fill="x")

    # ─── Mini / Widget Logic ─────────────────────────────────
    def toggle_mini_vault(self):
        if self.mini_vault and self.mini_vault.winfo_exists():
            if self.mini_vault.state() == "withdrawn":
                self.mini_vault.deiconify()
                self.mini_vault._refresh()
            else:
                self.mini_vault.withdraw()
        else:
            if self.data and self.key:
                self.mini_vault = MiniVault(self)
            else:
                self.restore_window()

    def minimize_to_widget(self):
        self.root.withdraw()
        if not self.floating_widget:
            self.floating_widget = FloatingWidget(self)
        self.floating_widget.deiconify()

    def restore_window(self):
        if self.mini_vault:
            try:
                self.mini_vault.withdraw()
            except Exception:
                pass
        self.root.deiconify()
        self.root.state("normal")
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        if self.floating_widget:
            self.floating_widget.withdraw()

    def quit_app(self):
        if self.mini_vault:
            try:
                self.mini_vault.destroy()
            except Exception:
                pass
        self.root.destroy()

    def _center(self, dlg, w, h):
        dlg.update_idletasks()
        cx = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        cy = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        dlg.geometry(f"{w}x{h}+{cx}+{cy}")

    def run(self):
        # Only start minimized if vault already exists (not first launch)
        if self.settings.get("start_minimized", False) and os.path.exists(DATA_FILE):
            self.root.after(200, self.minimize_to_widget)
        self.root.mainloop()


if __name__ == "__main__":
    PasswordVault().run()
