"""

🔐 Password Vault - Modern password manager for Windows (Apple Dark Style)

This is the main entry point. Utility modules live under ``password_vault/``.
"""


from __future__ import annotations

import customtkinter as ctk
import tkinter as tk

from tkinter import filedialog as tkfiledialog
import csv
import datetime
import hashlib
import hmac
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import uuid
import webbrowser

import pyperclip

from cryptography.fernet import InvalidToken

# ─── Package imports (modular code extracted into password_vault/) ─
from password_vault import APP_VERSION, APP_AUTHOR
from password_vault.theme import (
    CAT_EMOJIS, CARD_COLORS, BG, BG_SEC, BG_TERT, BG_GROUP, SEPARATOR,
    ACCENT, ACCENT_HOVER, GREEN, GREEN_HOVER, RED, RED_HOVER,
    ORANGE, ORANGE_HOVER, YELLOW, TEAL, PURPLE,
    TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT,
    BADGE_BG, INPUT_BG, CARD_HOVER, SIDEBAR_BG, SIDEBAR_SEL,
    cat_emoji,
)
from password_vault.settings import (
    AUTO_LOCK_MINUTES, MAX_LOGIN_ATTEMPTS, LOCKOUT_SECONDS,
    TRASH_DAYS, PASSWORD_AGE_WARNING,
    load_settings, save_settings,
)
from password_vault.crypto import (
    DATA_FILE, APP_DIR,
    get_or_create_salt, rotate_salt, derive_key, save_data, load_data,
)
from password_vault.security import (
    password_strength, password_age_text, find_duplicate_passwords,
    check_hibp_batch, calculate_security_score, generate_password,
)
from password_vault.export_import import (
    HAS_OPENPYXL, export_csv, export_excel, import_csv, import_excel,
)
from password_vault.ui.widgets import (
    tip, ios_group, ios_field, ios_combo, make_search_bar, safe_cfg,
    bind_right_click_recursive,
)
from password_vault.ui.mini_vault import MiniVault
from password_vault.ui.floating import FloatingWidget

# ─── Logging ──────────────────────────────────────────────────
log = logging.getLogger("PasswordVault")


# ═══════════════════════════════════════════════════════════════
#                     PASSWORD  VAULT
# ═══════════════════════════════════════════════════════════════
class PasswordVault:
    def __init__(self):
        self.key = None
        self.data = None
        self.floating_widget = None

        self.mini_vault = None
        self.current_category = "All"

        self._login_attempts = 0
        self._failed_streak = 0  # cumulative; doesn't reset on each lockout
        self._lockout_until = 0
        self._idle_timer = None
        self._main_frame = None
        self._clipboard_timer = None
        self._search_bar = None
        self._search_after_id = None

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

        except (tk.TclError, OSError):
            pass

        self._setup_input_helpers()
        self.show_login()

    # ─── Universal clipboard & right-click for all inputs ────
    def _setup_input_helpers(self):
        """Set up Ctrl+C/V/X/A (work with ANY keyboard language) and
        right-click context menu on every Entry / Text widget."""

        # ── Layout-independent Ctrl+C/V/X/A via Windows virtual-key codes ──
        # Virtual-key codes match the physical key regardless of keyboard
        # language (Arabic, Russian, etc.). This handler is Windows-specific:
        # other platforms get the standard Tk bindings, which already work
        # for Latin layouts.
        if sys.platform == "win32":
            _KC = {"c": 67, "v": 86, "x": 88, "a": 65}
            _LATIN = {"c": "c", "v": "v", "x": "x", "a": "a"}

            def _on_key(event):
                if not (event.state & 0x4):
                    return
                w = event.widget
                if not isinstance(w, (tk.Entry, tk.Text)):
                    return
                kc = event.keycode
                ks = event.keysym.lower()
                if kc == _KC["v"]:
                    if ks == _LATIN["v"]:
                        return
                    w.event_generate("<<Paste>>")
                    return "break"
                if kc == _KC["c"]:
                    if ks == _LATIN["c"]:
                        return
                    w.event_generate("<<Copy>>")
                    return "break"
                if kc == _KC["x"]:
                    if ks == _LATIN["x"]:
                        return
                    w.event_generate("<<Cut>>")
                    return "break"
                if kc == _KC["a"]:
                    if ks == _LATIN["a"]:
                        return
                    if isinstance(w, tk.Entry):
                        w.select_range(0, tk.END)
                        w.icursor(tk.END)
                    else:
                        w.tag_add("sel", "1.0", "end")
                    return "break"

            self.root.bind_all("<Key>", _on_key, add="+")

        # ── Right-click context menu ──────────────────────────
        def _ctx_menu(event):
            w = event.widget
            if not isinstance(w, (tk.Entry, tk.Text)):
                return

            # Give focus so selection is visible
            w.focus_set()

            menu = tk.Menu(w, tearoff=0, bg=BG_SEC, fg=TEXT_PRI,
                           activebackground=ACCENT, activeforeground="white",
                           font=("Segoe UI", 10))

            # Check selection
            has_sel = False
            try:
                if isinstance(w, tk.Entry):
                    has_sel = w.selection_present()
                else:
                    has_sel = bool(w.tag_ranges("sel"))
            except tk.TclError:
                pass

            # Check clipboard
            has_clip = True
            try:
                w.clipboard_get()
            except tk.TclError:
                has_clip = False

            menu.add_command(
                label="✂️  Cut",
                command=lambda: w.event_generate("<<Cut>>"),
                state="normal" if has_sel else "disabled")
            menu.add_command(
                label="📋  Copy",
                command=lambda: w.event_generate("<<Copy>>"),
                state="normal" if has_sel else "disabled")
            menu.add_command(
                label="📄  Paste",
                command=lambda: w.event_generate("<<Paste>>"),
                state="normal" if has_clip else "disabled")
            menu.add_separator()
            menu.add_command(
                label="🔤  Select All",
                command=lambda: _select_all(w))

            try:
                menu.post(event.x_root, event.y_root)
            except tk.TclError:
                pass

        def _select_all(w):
            try:
                if isinstance(w, tk.Entry):
                    w.select_range(0, tk.END)
                    w.icursor(tk.END)
                else:
                    w.tag_add("sel", "1.0", "end")
            except tk.TclError:
                pass

        # Bind to native Tk Entry and Text classes (covers CTkEntry/CTkTextbox)
        self.root.bind_class("Entry", "<Button-3>", _ctx_menu)
        self.root.bind_class("Text", "<Button-3>", _ctx_menu)

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
            self._idle_timer = self.root.after(
                mins * 60 * 1000, self._auto_lock)

    def _auto_lock(self):
        log.info("Vault auto-locked due to inactivity.")
        # Python strings are immutable; GC may retain copies of sensitive
        # data after refs drop. There's no portable way to securely wipe
        # them. Just release references and let the GC reclaim.
        self.key = None
        self.data = None
        self._idle_timer = None
        self._unbind_activity_events()
        self._unbind_shortcuts()
        if self.mini_vault:
            try:
                self.mini_vault.destroy()
            except tk.TclError:
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
                      fg_color="transparent").place(
            relx=0.5, rely=0.5, anchor="center")


        ctk.CTkLabel(self.login_frame, text="Password Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=30,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 4))

        is_new = not os.path.exists(DATA_FILE)

        ctk.CTkLabel(
            self.login_frame,
            text=("Create a master password" if is_new
                  else "Enter your master password"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SEC).pack(pady=(0, 24))

        pw_frame = ctk.CTkFrame(self.login_frame, fg_color="transparent")
        pw_frame.pack(pady=(0, 6))

        self.master_entry = ctk.CTkEntry(

            pw_frame, width=280, height=44,
            placeholder_text="Master Password", show="●",
            font=ctk.CTkFont(family="Segoe UI", size=14), justify="center",
            fg_color=BG_SEC, border_color=BG_TERT, border_width=1,
            corner_radius=12, text_color=TEXT_PRI)
        self.master_entry.pack(side="left")
        self.master_entry.bind("<Return>", lambda e: self.unlock())

        tip(self.master_entry,
            "Enter your master password to unlock the vault")

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

        self.error_label = ctk.CTkLabel(
            self.login_frame, text="", text_color=RED,
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
                sf, text="", font=ctk.CTkFont(size=10),
                text_color=TEXT_QUAT)
            self.strength_label.pack(side="left", padx=(8, 0))
            self.master_entry.bind("<KeyRelease>",
                                    self._update_login_strength)
            tip(self.strength_bar,
                "Shows how strong your password is")

            self.confirm_entry = ctk.CTkEntry(

                self.login_frame, width=320, height=44,
                placeholder_text="Confirm Password", show="●",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                justify="center", fg_color=BG_SEC,
                border_color=BG_TERT, border_width=1,
                corner_radius=12, text_color=TEXT_PRI)
            self.confirm_entry.pack(pady=(0, 10))
            self.confirm_entry.bind("<Return>", lambda e: self.unlock())

            tip(self.confirm_entry,
                "Re-enter your password to confirm")

        unlock_btn = ctk.CTkButton(
            self.login_frame,
            text="Unlock  🔓" if not is_new else "Create Vault  🔐",
            width=320, height=46,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=12,

            command=self.unlock)
        unlock_btn.pack(pady=(10, 0))
        tip(unlock_btn,
            "Decrypt and open your vault" if not is_new
            else "Create a new encrypted vault")

        self.master_entry.focus()


    def _update_login_strength(self, event=None):
        s, lbl, c = password_strength(self.master_entry.get())
        self.strength_bar.set(s / 4)
        self.strength_bar.configure(progress_color=c)
        self.strength_label.configure(text=lbl, text_color=c)

    def _validate_master_password(self, pw):
        if len(pw) < 12:
            return "⚠️ Too short (min 12 chars for master password)"
        if not any(c.isupper() for c in pw):
            return "⚠️ Need at least one uppercase letter"
        if not any(c.islower() for c in pw):
            return "⚠️ Need at least one lowercase letter"
        if not any(c.isdigit() for c in pw):
            return "⚠️ Need at least one digit"
        score, _, _ = password_strength(pw)
        if score < 3:
            return "⚠️ Master password is not strong enough"
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

                self.error_label.configure(
                    text="⚠️ Passwords don't match")
                return

            err = self._validate_master_password(pw)
            if err:
                self.error_label.configure(text=err)
                return


        salt = get_or_create_salt()
        self.key = derive_key(pw, salt)

        max_att = self.settings.get("max_login_attempts",
                                     MAX_LOGIN_ATTEMPTS)
        lock_sec = self.settings.get("lockout_seconds", LOCKOUT_SECONDS)
        try:
            self.data = load_data(self.key)

        except InvalidToken:
            self._login_attempts += 1
            self._failed_streak += 1
            log.warning("Failed login attempt #%d (streak %d).",
                        self._login_attempts, self._failed_streak)
            rem = max_att - self._login_attempts
            if self._login_attempts >= max_att:
                # Exponential backoff per cumulative streak.
                # streak 5 → 1x, 10 → 2x, 15 → 4x, 20 → 8x (capped at 30 min)
                tier = max(0, (self._failed_streak // max_att) - 1)
                penalty = lock_sec * (2 ** min(tier, 6))
                penalty = min(penalty, 1800)
                self._lockout_until = time.time() + penalty
                log.warning("Account locked out for %ds (streak %d).",
                            penalty, self._failed_streak)
                self.error_label.configure(
                    text=f"⚠️ Locked for {penalty}s")
                self._login_attempts = 0  # reset window, keep streak
            else:
                self.error_label.configure(
                    text=f"⚠️ Wrong password ({rem} attempts left)")
            return

        self._login_attempts = 0
        self._failed_streak = 0  # success — reset escalation
        log.info("Vault unlocked successfully%s.",
                 " (new vault created)" if is_new else "")
        if is_new:
            save_data(self.data, self.key)
        self.login_frame.destroy()
        self.build_ui()

        self._start_idle_timer()
        self._bind_shortcuts()

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
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(side="left")

        self.search_var = ctk.StringVar()

        self.search_var.trace_add("write",
                                   lambda *_: self._debounced_refresh())

        self._search_bar = make_search_bar(
            top, self.search_var,
            lambda: (self.data.get("categories", [])
                     if self.data else []),
            self._search_cat_filter,
            height=32, width=260)
        self._search_bar.pack(side="left", padx=16)

        # Settings
        settings_btn = ctk.CTkButton(
            top, text="⚙", width=32, height=32,
            font=ctk.CTkFont(size=15), fg_color="transparent",
            hover_color=BG_TERT, corner_radius=8, text_color=TEXT_SEC,
            command=self.show_settings_menu)
        settings_btn.pack(side="right", padx=(0, 10))
        tip(settings_btn,
            "Settings — Preferences, export/import, security dashboard")

        add_btn = ctk.CTkButton(
            top, text="＋  Add New", width=110, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
            command=lambda: self.show_entry_dialog())
        add_btn.pack(side="right", padx=(0, 6))
        tip(add_btn, "Add a new password entry  (Ctrl+N)")

        # Content

        content = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Sidebar

        self.sidebar = ctk.CTkFrame(content, width=200,
                                      fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)


        ctk.CTkLabel(self.sidebar, text="Categories",
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_SEC).pack(
            pady=(16, 8), padx=16, anchor="w")


        self.cat_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=SIDEBAR_BG)
        self.cat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))


        add_cat_btn = ctk.CTkButton(
            self.sidebar, text="＋  Category", height=30,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", border_width=1,
            border_color=TEXT_QUAT, corner_radius=8,
            hover_color=BG_TERT, text_color=TEXT_SEC,
            command=self.show_add_cat_dialog)
        add_cat_btn.pack(pady=(0, 10), padx=12, fill="x")
        tip(add_cat_btn,
            "Create a new category to organize passwords")

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

    def _debounced_refresh(self):
        """Debounce search-triggered refreshes — 300ms idle then refresh."""
        if self._search_after_id:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.root.after(300, self.refresh_entries)

    # ─── Keyboard Shortcuts ──────────────────────────────────
    def _bind_shortcuts(self):
        self.root.bind("<Control-n>",
                        lambda e: self.show_entry_dialog())
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<Control-l>", lambda e: self._auto_lock())
        self.root.bind("<Control-e>",
                        lambda e: self.show_export_dialog())
        self.root.bind("<Control-i>",
                        lambda e: self.show_import_dialog())

    def _unbind_shortcuts(self):
        for sc in ("<Control-n>", "<Control-f>", "<Control-l>",
                   "<Control-e>", "<Control-i>"):
            try:
                self.root.unbind(sc)
            except tk.TclError:
                pass

    def _focus_search(self):
        if self._search_bar:
            try:
                self._search_bar._entry.focus_set()
            except (tk.TclError, AttributeError):
                pass

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
        menu.add_command(label="🛡️  Security Dashboard",
                          command=self.show_security_dashboard)
        menu.add_separator()
        menu.add_command(label="📤  Export Data  (Ctrl+E)",
                          command=self.show_export_dialog)
        menu.add_command(label="📥  Import Data  (Ctrl+I)",
                          command=self.show_import_dialog)
        trash_n = len(self.data.get("trash", []))
        menu.add_command(
            label=f"🗑️  Recycle Bin ({trash_n})",
            command=self.show_trash_dialog)
        menu.add_separator()
        menu.add_command(label="🔒  Lock Vault  (Ctrl+L)",
                          command=self._auto_lock)
        menu.add_separator()
        menu.add_command(label="ℹ️  About",
                          command=self.show_about_dialog)
        try:
            menu.post(self.root.winfo_pointerx(),
                      self.root.winfo_pointery())
        except tk.TclError:
            pass

    # ─── About Dialog ────────────────────────────────────────
    def show_about_dialog(self):
        dlg = self._make_dialog("About Password Vault", 380, 440)

        circle = ctk.CTkFrame(dlg, width=80, height=80,
                                corner_radius=40, fg_color=ACCENT)
        circle.pack(pady=(24, 10))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="🔐", font=ctk.CTkFont(size=36),
                      fg_color="transparent").place(
            relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(dlg, text="Password Vault",
                      font=ctk.CTkFont(family="Segoe UI", size=22,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 2))

        ver_frame = ctk.CTkFrame(dlg, fg_color=ACCENT, corner_radius=12)
        ver_frame.pack(pady=(0, 14))
        ctk.CTkLabel(ver_frame, text=f"  v{APP_VERSION}  ",
                      font=ctk.CTkFont(family="Segoe UI", size=11,
                                        weight="bold"),
                      text_color="white").pack(padx=8, pady=2)

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
                          font=ctk.CTkFont(family="Segoe UI", size=12,
                                            weight="bold"),
                          text_color=TEXT_PRI, anchor="e").pack(side="right")

        info_row(g, "📦", "Version", f"v{APP_VERSION}", idx=0)
        info_row(g, "👨‍💻", "Developer", APP_AUTHOR, idx=1)
        info_row(g, "🛡️", "Encryption", "AES-256 (Fernet)", idx=2)
        info_row(g, "🔑", "Key Derivation", "PBKDF2-SHA256", idx=3)
        info_row(g, "📂", "Data Location", "%APPDATA%", idx=4)

        g2 = ios_group(dlg, "Features")
        features = [
            "🔐  AES-256 encrypted local vault",
            "🎲  Secure password generator",
            "🔒  Auto-lock & brute-force protection",
            "📋  Quick-copy with auto-clear clipboard",
            "🎨  Custom card colors & categories",
            "📌  Favorites, Pin & Mini Vault",
            "🌐  URL field with browser open",
            "📤  Export / Import (CSV & Excel)",
            "🗑️  Recycle Bin for deleted entries",
            "🛡️  Security Dashboard & Breach Check",
            "⌨️  Keyboard shortcuts",
        ]
        for i, feat in enumerate(features):
            if i > 0:
                ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
                    fill="x", padx=(16, 0))
            ctk.CTkLabel(g2, text=feat,
                          font=ctk.CTkFont(family="Segoe UI", size=11),
                          text_color=TEXT_PRI, anchor="w").pack(
                fill="x", padx=12, pady=3)

        ctk.CTkButton(
            dlg, text="Close", height=36, width=140,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=BG_TERT, hover_color=CARD_HOVER, corner_radius=10,
            command=dlg.destroy).pack(pady=(14, 16))

    # ─── Settings Dialog ─────────────────────────────────────
    def show_settings_dialog(self):
        dlg = self._make_dialog("Settings", 480, 620)

        ctk.CTkLabel(dlg, text="⚙️  Settings",
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                         scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        s = dict(self.settings)

        def setting_row(group, icon, label, idx=0):
            if idx > 0:
                ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
                    fill="x", padx=(46, 0))
            row = ctk.CTkFrame(group, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=5)
            lbl_w = ctk.CTkLabel(
                row, text=f"{icon}  {label}",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_PRI, anchor="w")
            lbl_w.pack(side="left", fill="x", expand=True)
            return row, lbl_w

        # ── SECURITY ──
        g_sec = ios_group(scroll, "Security")

        r, lbl = setting_row(g_sec, "🔒", "Auto-Lock", idx=0)
        al_map = {"1 min": 1, "2 min": 2, "5 min": 5,
                  "10 min": 10, "15 min": 15, "30 min": 30, "Never": 0}
        al_rev = {v: k for k, v in al_map.items()}
        al_var = ctk.StringVar(
            value=al_rev.get(s["auto_lock_minutes"], "5 min"))
        al_opt = ctk.CTkOptionMenu(
            r, values=list(al_map.keys()), variable=al_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        al_opt.pack(side="right")
        tip(lbl, "Lock the vault after this period of inactivity. "
                 "'Never' disables auto-lock.")

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
        tip(lbl2, "Maximum wrong password attempts before lockout.")

        r3, lbl3 = setting_row(g_sec, "⏱️", "Lockout Duration", idx=2)
        lo_map = {"15 sec": 15, "30 sec": 30, "60 sec": 60,
                  "2 min": 120, "5 min": 300}
        lo_rev = {v: k for k, v in lo_map.items()}
        lo_var = ctk.StringVar(
            value=lo_rev.get(s["lockout_seconds"], "30 sec"))
        lo_opt = ctk.CTkOptionMenu(
            r3, values=list(lo_map.keys()), variable=lo_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        lo_opt.pack(side="right")
        tip(lbl3, "How long the vault stays locked after "
                  "too many failed attempts.")

        r4, lbl4 = setting_row(g_sec, "📋", "Clear Clipboard", idx=3)
        cl_map = {"Off": 0, "10 sec": 10, "15 sec": 15,
                  "30 sec": 30, "60 sec": 60}
        cl_rev = {v: k for k, v in cl_map.items()}
        cl_var = ctk.StringVar(
            value=cl_rev.get(s["clipboard_clear_seconds"], "Off"))
        cl_opt = ctk.CTkOptionMenu(
            r4, values=list(cl_map.keys()), variable=cl_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        cl_opt.pack(side="right")
        tip(lbl4, "Automatically clear copied passwords "
                  "from clipboard after this time.")

        # ── PASSWORD GENERATOR ──
        g_gen = ios_group(scroll, "Password Generator Defaults")

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

        r6, lbl6 = setting_row(g_gen, "🔤", "Uppercase (ABC)", idx=1)
        gen_upper = ctk.CTkSwitch(r6, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_upper.pack(side="right")
        if s.get("gen_upper", True):
            gen_upper.select()
        tip(lbl6, "Include uppercase letters (A-Z).")

        r7, lbl7 = setting_row(g_gen, "🔡", "Lowercase (abc)", idx=2)
        gen_lower = ctk.CTkSwitch(r7, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_lower.pack(side="right")
        if s.get("gen_lower", True):
            gen_lower.select()
        tip(lbl7, "Include lowercase letters (a-z).")

        r8, lbl8 = setting_row(g_gen, "🔢", "Digits (0-9)", idx=3)
        gen_digits = ctk.CTkSwitch(r8, text="", width=46,
                                     fg_color=BG_TERT, progress_color=GREEN,
                                     button_color=TEXT_PRI)
        gen_digits.pack(side="right")
        if s.get("gen_digits", True):
            gen_digits.select()
        tip(lbl8, "Include digits (0-9).")

        r9, lbl9 = setting_row(g_gen, "🔣", "Symbols (#$%&)", idx=4)
        gen_symbols = ctk.CTkSwitch(r9, text="", width=46,
                                      fg_color=BG_TERT, progress_color=GREEN,
                                      button_color=TEXT_PRI)
        gen_symbols.pack(side="right")
        if s.get("gen_symbols", True):
            gen_symbols.select()
        tip(lbl9, "Include special symbols (!@#$%&).")

        # ── APPEARANCE ──
        g_app = ios_group(scroll, "Appearance")

        r10, lbl10 = setting_row(g_app, "🎨", "Default Card Color", idx=0)
        tip(lbl10, "Default color for new password entries.")

        def_color_var = ctk.StringVar(
            value=s.get("default_card_color", "default"))
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
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="white",
                command=lambda k=ckey: _sel_def_color(k))
            b.pack(side="left", padx=3)
            color_btns[ckey] = b
            tip(b, f"{info['label']} — set as default card color")

        def _sel_def_color(k):
            def_color_var.set(k)
            for ck, cb in color_btns.items():
                cb.configure(text="✓" if ck == k else "")

        # ── BEHAVIOR ──
        g_beh = ios_group(scroll, "Behavior")

        r11, lbl11 = setting_row(g_beh, "🚀", "Start Minimized", idx=0)
        start_min = ctk.CTkSwitch(r11, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        start_min.pack(side="right")
        if s.get("start_minimized", False):
            start_min.select()
        tip(lbl11, "Start the app minimized to the floating widget.")

        # ── SAVE ──
        def apply_settings():
            self.settings["auto_lock_minutes"] = al_map.get(
                al_var.get(), 5)
            self.settings["max_login_attempts"] = int(att_var.get())
            self.settings["lockout_seconds"] = lo_map.get(
                lo_var.get(), 30)
            self.settings["clipboard_clear_seconds"] = cl_map.get(
                cl_var.get(), 0)
            self.settings["gen_length"] = gl_var.get()
            self.settings["gen_upper"] = bool(gen_upper.get())
            self.settings["gen_lower"] = bool(gen_lower.get())
            self.settings["gen_digits"] = bool(gen_digits.get())
            self.settings["gen_symbols"] = bool(gen_symbols.get())
            self.settings["default_card_color"] = def_color_var.get()
            self.settings["start_minimized"] = bool(start_min.get())
            save_settings(self.settings)
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
        dlg = self._make_dialog("Change Master Password", 400, 380)

        ctk.CTkLabel(dlg, text="🔑", font=ctk.CTkFont(size=32)).pack(
            pady=(16, 2))
        ctk.CTkLabel(
            dlg, text="Change Master Password",
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
                                  fg_color=BG_TERT,
                                  progress_color=TEXT_QUAT)
        sb.pack(side="left", fill="x", expand=True)
        sb.set(0)
        sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                            text_color=TEXT_QUAT)
        sl.pack(side="left", padx=(6, 0))

        def upd(e=None):
            s, l, c = password_strength(new_e.get())
            sb.set(s / 4)
            sb.configure(progress_color=c)
            sl.configure(text=l, text_color=c)

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
            if not hmac.compare_digest(derive_key(op, salt), self.key):
                err.configure(text="⚠️ Current password is wrong")
                return
            if np_ != cp:
                err.configure(text="⚠️ New passwords don't match")
                return
            ve = self._validate_master_password(np_)
            if ve:
                err.configure(text=ve)
                return
            # Rotate salt + re-derive key + re-encrypt vault. Atomic order:
            # 1) compute new key with new salt
            # 2) save vault encrypted with new key (atomic write to .tmp)
            # 3) only after save succeeds, persist new salt
            # If step 2 fails, salt is unchanged and old key still works.
            new_salt = os.urandom(32)
            new_key = derive_key(np_, new_salt)
            try:
                save_data(self.data, new_key)
            except (OSError, ValueError) as exc:
                log.error("Re-encrypt during password change failed: %s",
                          exc, exc_info=True)
                err.configure(text="⚠️ Could not save — try again")
                return
            # Vault is now encrypted with new_key. Persist the salt.
            rotate_salt(new_salt)
            self.key = new_key
            log.info("Master password changed; salt rotated.")
            dlg.destroy()

        save_btn = ctk.CTkButton(
            frm, text="Change Password", height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ORANGE, hover_color=ORANGE_HOVER, corner_radius=10,
            command=save)
        save_btn.pack(fill="x", padx=14)
        tip(save_btn, "Save the new master password")
        dlg.bind("<Return>", lambda _e: save())
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
                font=ctk.CTkFont(
                    family="Segoe UI", size=12,
                    weight="bold" if active else "normal"),
                fg_color=SIDEBAR_SEL if active else "transparent",
                hover_color=(ACCENT_HOVER if active else BG_TERT),
                text_color="white" if active else TEXT_PRI,
                anchor="w", height=34, corner_radius=8,
                command=lambda c=cat: self.select_cat(c))
            btn.pack(side="left", fill="x", expand=True)
            tip(btn,
                f"Show {'all entries' if cat == 'All' else f'entries in {cat}'}")

            if cat != "All":
                del_btn = ctk.CTkButton(
                    row, text="✕", width=26, height=26,
                    font=ctk.CTkFont(size=10), fg_color="transparent",
                    hover_color=RED_HOVER, corner_radius=6,
                    text_color=TEXT_TERT,
                    command=lambda c=cat: self.confirm_delete_category(c))
                del_btn.pack(side="right", padx=(2, 0))
                tip(del_btn, f"Delete '{cat}' category")

    def select_cat(self, cat):
        self.current_category = cat
        self.refresh_categories()
        self.refresh_entries()


    # ─── Delete Category ─────────────────────────────────────
    def confirm_delete_category(self, cat_name):
        n = sum(1 for e in self.data["entries"]
                if e.get("category") == cat_name)
        dlg = self._make_dialog("Delete Category", 380, 190)

        ctk.CTkLabel(dlg, text="⚠️  Delete Category?",
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(20, 4))
        msg = f'Delete "{cat_name}"?'
        if n > 0:
            msg += f'\n{n} entries → "General".'
        ctk.CTkLabel(dlg, text=msg, font=ctk.CTkFont(size=12),
                      text_color=TEXT_SEC, justify="center").pack(
            pady=(0, 14))

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
            width=140, height=36, font=ctk.CTkFont(size=13),
            corner_radius=10, command=do_del).pack(side="left", padx=4)
        ctk.CTkButton(
            bf, text="Cancel", fg_color=BG_TERT,
            hover_color=CARD_HOVER, width=140, height=36,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=dlg.destroy).pack(side="right", padx=4)
        dlg.bind("<Return>", lambda _e: do_del())

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
                       or search in e.get("url", "").lower()
                       or search in e.get("category", "").lower()
                       or search in e.get("notes", "").lower()]
        # pinned first, then alphabetically
        entries.sort(key=lambda e: (not e.get("pinned", False),
                                     e.get("title", "").lower()))
        if not entries:

            ef = ctk.CTkFrame(self.entries_panel, fg_color="transparent")
            ef.pack(expand=True, fill="both")
            ctk.CTkLabel(ef, text="📭",
                          font=ctk.CTkFont(size=48)).pack(pady=(80, 8))
            ctk.CTkLabel(ef, text="No passwords yet",
                          font=ctk.CTkFont(family="Segoe UI", size=15),
                          text_color=TEXT_TERT).pack()
            ctk.CTkLabel(ef,
                          text="Click '＋ Add New' to get started",
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

        def _on_right_click(event, e=entry):
            self._show_context_menu(event, e)

        if cc["strip"]:
            ctk.CTkFrame(card, width=3, fg_color=cc["strip"],
                          corner_radius=2).place(
                x=3, y=6, relheight=0.78)

        inner = ctk.CTkFrame(card, fg_color="transparent")

        inner.pack(fill="x", padx=(14 if cc["strip"] else 12), pady=6)


        # Row 1: Pin + Title + Category badge + Age + Edit + Delete
        r1 = ctk.CTkFrame(inner, fg_color="transparent")

        r1.pack(fill="x", pady=(0, 2))

        # Pin toggle
        is_pinned = entry.get("pinned", False)
        pin_btn = ctk.CTkButton(
            r1, text="📌" if is_pinned else "○",
            width=24, height=24, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5,
            font=ctk.CTkFont(size=11 if is_pinned else 9),
            text_color=YELLOW if is_pinned else TEXT_QUAT,
            command=lambda: self._toggle_pin(entry))
        pin_btn.pack(side="left", padx=(0, 2))
        tip(pin_btn,
            "Unpin from top" if is_pinned else "Pin to top")

        emoji = cat_emoji(entry.get("category", ""))

        ctk.CTkLabel(r1, text=f"{emoji}  {entry.get('title', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=13,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(side="left")
        ctk.CTkLabel(r1, text=f" {entry.get('category', '')} ",
                      font=ctk.CTkFont(family="Segoe UI", size=9),
                      text_color=TEXT_SEC, fg_color=BADGE_BG,
                      corner_radius=4).pack(side="left", padx=(8, 0))

        # Delete
        del_btn = ctk.CTkButton(
            r1, text="🗑", width=24, height=24, fg_color="transparent",
            hover_color=RED_HOVER, corner_radius=5,
            font=ctk.CTkFont(size=11),
            command=lambda: self.confirm_delete(entry))
        del_btn.pack(side="right", padx=1)
        tip(del_btn, "Move to Recycle Bin")

        # Edit
        edit_btn = ctk.CTkButton(
            r1, text="✏", width=24, height=24, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5,
            font=ctk.CTkFont(size=11),
            command=lambda: self.show_entry_dialog(entry))
        edit_btn.pack(side="right", padx=1)
        tip(edit_btn, "Edit this entry")

        # Age
        age_t, age_c = password_age_text(
            entry.get("modified_at") or entry.get("created_at"))
        if age_t:
            ctk.CTkLabel(r1, text=age_t, font=ctk.CTkFont(size=9),
                          text_color=age_c).pack(
                side="right", padx=(0, 6))

        # Row 2: User + Copy user + URL + Password + Eye + Copy pass
        r2 = ctk.CTkFrame(inner, fg_color="transparent")

        r2.pack(fill="x", pady=(0, 1))

        ctk.CTkLabel(r2, text=f"👤 {entry.get('username', '')}",
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_SEC, anchor="w").pack(side="left")
        cu = ctk.CTkButton(
            r2, text="📋", width=28, height=22,
            font=ctk.CTkFont(size=10),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=5,
                            command=lambda: self._copy(entry.get("username", ""), cu))

        cu.pack(side="left", padx=(6, 0))
        tip(cu, "Copy username")

        # URL button
        url = entry.get("url", "")
        if url:
            url_btn = ctk.CTkButton(
                r2, text="🌐", width=28, height=22,
                font=ctk.CTkFont(size=10),
                fg_color=BG_TERT, hover_color=TEXT_QUAT,
                text_color=TEAL, corner_radius=5,
                command=lambda u=url: webbrowser.open(u))
            url_btn.pack(side="left", padx=(4, 0))
            tip(url_btn, f"Open {url}")

        pwd = entry.get("password", "")

        cp = ctk.CTkButton(
            r2, text="🔑 Copy", width=65, height=22,
            font=ctk.CTkFont(size=10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white", corner_radius=5,
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
            hover_color=BG_TERT, corner_radius=5,
            font=ctk.CTkFont(size=10), command=toggle)
        eye.pack(side="right", padx=(0, 2))
        tip(eye, "Show / hide password")

        # Row 3: URL text (subtle, if exists)
        if url:
            ctk.CTkLabel(inner,
                          text=f"🔗 {url[:60]}{'…' if len(url) > 60 else ''}",
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEAL, anchor="w", cursor="hand2").pack(
                fill="x", pady=(1, 0))

        # Row 4: Notes
        notes = entry.get("notes", "")
        if notes:

            ctk.CTkLabel(inner, text=notes,
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEXT_TERT, anchor="w",
                          wraplength=400, justify="left").pack(
                fill="x", pady=(2, 0))

        # Bind right-click to the entire card and every child so the menu
        # opens regardless of where on the card the user clicks.
        bind_right_click_recursive(card, _on_right_click)

    def _toggle_pin(self, entry):
        entry["pinned"] = not entry.get("pinned", False)
        save_data(self.data, self.key)
        self.refresh_entries()

    def _save_and_refresh(self):
        """Save data and refresh all views (entries + categories + mini vault)."""
        save_data(self.data, self.key)
        self.refresh_categories()
        self.refresh_entries()
        if (self.mini_vault
                and self.mini_vault.winfo_exists()):
            try:
                self.mini_vault._refresh()
            except tk.TclError:
                pass

    def _copy(self, text, btn):

        self._copy_to_clipboard(text, btn)

    def _clear_clipboard(self):
        try:
            pyperclip.copy("")
        except (OSError, RuntimeError):
            pass
        self._clipboard_timer = None

    # ─── Right-Click Context Menu ─────────────────────────────
    def _show_context_menu(self, event, entry, parent=None):
        """Show a right-click context menu for a password entry card."""
        self._reset_idle()
        owner = parent or self.root
        menu = tk.Menu(owner, tearoff=0,
                       bg=BG_SEC, fg=TEXT_PRI,
                       activebackground=ACCENT,
                       activeforeground="white",
                       font=("Segoe UI", 10),
                       relief="flat", bd=1,
                       selectcolor=ACCENT)

        username = entry.get("username", "")
        password = entry.get("password", "")
        url = entry.get("url", "")
        title = entry.get("title", "")

        # ── Copy actions ──
        menu.add_command(
            label="📋  Copy Username",
            command=lambda: self._ctx_copy(username, "Username"))
        menu.add_command(
            label="🔑  Copy Password",
            command=lambda: self._ctx_copy(password, "Password"))

        menu.add_separator()

        # ── URL / Browser ──
        if url:
            menu.add_command(
                label="🌐  Open URL in Browser",
                command=lambda: webbrowser.open(url))
            menu.add_command(
                label="🌐  Open URL + Copy Username",
                command=lambda: self._open_url_with_creds(
                    url, username, password))
        else:
            menu.add_command(
                label="🌐  Open URL in Browser",
                state="disabled")

        # ── SSH / RDP Session ── only show when the entry looks like a
        # remote host (URL field is set, or category hints at servers).
        host = self._extract_host(url, entry)
        cat = entry.get("category", "").lower()
        looks_remote = bool(host) or cat in ("server", "vpn", "ssh", "rdp")
        if looks_remote:
            menu.add_separator()
            menu.add_command(
                label="🖥️  SSH Session …",
                command=lambda: self._show_ssh_dialog(entry))
            menu.add_command(
                label="🖥️  RDP Session …",
                command=lambda: self._show_rdp_dialog(entry))

        menu.add_separator()

        # ── Edit / Delete ──
        menu.add_command(
            label="✏️  Edit Entry",
            command=lambda: self.show_entry_dialog(entry))
        menu.add_command(
            label="📌  Pin / Unpin",
            command=lambda: self._toggle_pin(entry))
        menu.add_command(
            label="🗑️  Delete",
            command=lambda: self.confirm_delete(entry))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _ctx_copy(self, text, label=""):
        """Copy text to clipboard with optional notification."""
        self._copy_to_clipboard(text)

    @staticmethod
    def _extract_host(url, entry):
        """Extract hostname/IP from URL or entry fields for SSH/RDP."""
        if url:
            raw = url.strip()
            # urlsplit needs a scheme to populate hostname; add a fake one if missing
            if "://" not in raw:
                raw = "ssh://" + raw
            try:
                parts = urllib.parse.urlsplit(raw)
                host = parts.hostname or ""
            except ValueError:
                host = ""
            if host:
                return host
        # Try from title (some people put IP/hostname in title)
        title = entry.get("title", "").strip()
        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        if ip_pattern.match(title):
            return title
        return ""

    def _open_url_with_creds(self, url, username, password):
        """Open URL in browser, copy username to clipboard.

        Password is NOT auto-copied — clipboard hijacking is dangerous and
        can silently overwrite content the user copied in the meantime.
        Use the 'Copy Password' menu/button when ready instead.
        """
        self._copy_to_clipboard(username)
        webbrowser.open(url)

    # ─── Detect available SSH/RDP clients ────────────────────
    @staticmethod
    def _detect_ssh_clients():
        """Detect available SSH clients on the system."""
        clients = []
        # PuTTY
        putty_paths = [
            os.path.join(os.environ.get("ProgramFiles", ""),
                         "PuTTY", "putty.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                         "PuTTY", "putty.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "PuTTY", "putty.exe"),
        ]
        for p in putty_paths:
            if p and os.path.isfile(p):
                clients.append(("PuTTY", p))
                break

        # MobaXterm
        moba_paths = [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                         "Mobatek", "MobaXterm", "MobaXterm.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""),
                         "Mobatek", "MobaXterm", "MobaXterm.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "MobaXterm", "MobaXterm.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                         "Mobatek", "MobaXterm",
                         "MobaXterm_Personal.exe"),
        ]
        for p in moba_paths:
            if p and os.path.isfile(p):
                clients.append(("MobaXterm", p))
                break

        # Windows built-in SSH
        win_ssh = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                               "System32", "OpenSSH", "ssh.exe")
        if os.path.isfile(win_ssh):
            clients.append(("Windows SSH", win_ssh))
        else:
            # ssh.exe might be on PATH
            found = shutil.which("ssh")
            if found:
                clients.append(("Windows SSH", found))

        return clients

    # ─── SSH Connection Dialog ─────────────────────────────
    def _show_ssh_dialog(self, entry):
        """Show a dialog to configure and start an SSH session."""
        dlg = self._make_dialog("SSH Session", 420, 480)

        ctk.CTkLabel(
            dlg, text="🖥️  SSH Session",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(12, 2))
        ctk.CTkLabel(
            dlg, text=f"Entry: {entry.get('title', '')}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_SEC).pack(pady=(0, 8))

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 6))

        # Host / IP
        pre_host = self._extract_host(entry.get("url", ""), entry)
        ctk.CTkLabel(form, text="Host / IP",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(4, 1))
        host_e = ctk.CTkEntry(
            form, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI,
            placeholder_text="e.g. 192.168.1.10 or server.example.com")
        host_e.pack(fill="x", pady=(0, 6))
        if pre_host:
            host_e.insert(0, pre_host)

        # Username
        ctk.CTkLabel(form, text="Username",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(2, 1))
        user_e = ctk.CTkEntry(
            form, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI, placeholder_text="username")
        user_e.pack(fill="x", pady=(0, 6))
        user_e.insert(0, entry.get("username", ""))

        # Port
        port_row = ctk.CTkFrame(form, fg_color="transparent")
        port_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(port_row, text="Port",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            side="left")
        port_e = ctk.CTkEntry(
            port_row, width=80, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI)
        port_e.pack(side="left", padx=(10, 0))
        # Pre-fill port from URL
        pre_port = self._extract_port(entry.get("url", ""), 22)
        port_e.insert(0, str(pre_port))

        # SSH Client selector
        clients = self._detect_ssh_clients()
        client_names = [c[0] for c in clients] if clients else ["No SSH client found"]
        ctk.CTkLabel(form, text="SSH Client",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(2, 1))
        client_var = ctk.StringVar(value=client_names[0])
        client_cb = ctk.CTkComboBox(
            form, values=client_names, variable=client_var,
            height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_SEC, dropdown_hover_color=ACCENT,
            text_color=TEXT_PRI, state="readonly")
        client_cb.pack(fill="x", pady=(0, 8))

        # Error label
        err = ctk.CTkLabel(form, text="", text_color=RED,
                            font=ctk.CTkFont(size=10), height=14)
        err.pack(fill="x", pady=(0, 2))

        # Info label
        info_lbl = ctk.CTkLabel(
            form, text="💡 Password will be copied to clipboard",
            font=ctk.CTkFont(size=9), text_color=TEXT_TERT)
        info_lbl.pack(fill="x")

        def connect():
            host = host_e.get().strip()
            user = user_e.get().strip()
            port_str = port_e.get().strip()

            if not host:
                err.configure(text="⚠️ Host / IP is required")
                return

            try:
                port = int(port_str)
            except ValueError:
                err.configure(text="⚠️ Invalid port number")
                return

            if not clients:
                err.configure(text="⚠️ No SSH client found on system")
                return

            selected = client_var.get()
            client_path = ""
            for name, path in clients:
                if name == selected:
                    client_path = path
                    break
            if not client_path:
                err.configure(text="⚠️ SSH client not found")
                return

            # Stage password briefly (10s) so user can paste, then auto-clear
            self._copy_to_clipboard(entry.get("password", ""),
                                     force_clear_seconds=10)

            dlg.destroy()

            self._launch_ssh(client_path, selected, host, user,
                             port, entry.get("title", ""))

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkButton(
            btn_row, text="Cancel", width=90, height=36,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
            command=dlg.destroy).pack(side="left")
        connect_btn = ctk.CTkButton(
            btn_row, text="🖥️  Connect", height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER,
            text_color=BG, corner_radius=8,
            command=connect)
        connect_btn.pack(side="right", fill="x", expand=True, padx=(8, 0))
        tip(connect_btn, "Start SSH session (password copied to clipboard)")
        dlg.bind("<Return>", lambda _e: connect())

        host_e.focus()

    @staticmethod
    def _extract_port(url, default=22):
        """Extract port number from URL string."""
        if not url:
            return default
        raw = url.strip()
        if "://" not in raw:
            raw = "ssh://" + raw
        try:
            parts = urllib.parse.urlsplit(raw)
            return parts.port or default
        except ValueError:
            return default

    @staticmethod
    def _sanitize_shell_arg(value: str) -> str:
        """Remove dangerous characters from a value used in shell args."""
        # Allow alphanumeric, dots, hyphens, underscores, @, colons,
        # backslash (for domain\user), forward slash
        return re.sub(r'[^a-zA-Z0-9.\-_@:/\\ ]', '', value)

    def _launch_ssh(self, client_path, client_name, host, user, port, title):
        """Launch SSH session using the selected client."""
        # Sanitize all user-supplied values to prevent command injection
        host = self._sanitize_shell_arg(host)
        user = self._sanitize_shell_arg(user)
        port = int(port)
        try:
            if client_name == "PuTTY":
                cmd = [client_path, "-ssh"]
                if user:
                    cmd += ["-l", user]
                if port != 22:
                    cmd += ["-P", str(port)]
                cmd.append(host)
                subprocess.Popen(cmd)

            elif client_name == "MobaXterm":
                # Use -l flag to preserve backslash in domain\user
                ssh_parts = ["ssh"]
                if user:
                    # Single-quote the username so MobaXterm's internal
                    # bash does not interpret the backslash as escape
                    safe_user = user.replace("'", "'\\''")
                    ssh_parts += ["-l", f"'{safe_user}'"]
                if port != 22:
                    ssh_parts += ["-p", str(port)]
                ssh_parts.append(host)
                subprocess.Popen([client_path, "-newtab",
                                  " ".join(ssh_parts)])

            elif client_name == "Windows SSH":
                # Use -l flag to preserve backslash in domain\user
                cmd = [client_path]
                if user:
                    cmd += ["-l", user]
                cmd.append(host)
                if port != 22:
                    cmd += ["-p", str(port)]
                # Open in a new visible console window
                subprocess.Popen(
                    ["cmd", "/c", "start",
                     self._sanitize_shell_arg(
                         f"SSH - {title} ({host})"),
                     "cmd", "/k"] + cmd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
        except OSError as exc:
            log.warning("Failed to launch SSH client %s: %s",
                        client_name, exc)

    # ─── RDP Connection Dialog ─────────────────────────────
    def _show_rdp_dialog(self, entry):
        """Show a dialog to configure and start an RDP session."""
        dlg = self._make_dialog("RDP Session", 420, 400)

        ctk.CTkLabel(
            dlg, text="🖥️  Remote Desktop (RDP)",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(12, 2))
        ctk.CTkLabel(
            dlg, text=f"Entry: {entry.get('title', '')}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_SEC).pack(pady=(0, 8))

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 6))

        # Host / IP
        pre_host = self._extract_host(entry.get("url", ""), entry)
        ctk.CTkLabel(form, text="Host / IP",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(4, 1))
        host_e = ctk.CTkEntry(
            form, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI,
            placeholder_text="e.g. 192.168.1.10 or server.example.com")
        host_e.pack(fill="x", pady=(0, 6))
        if pre_host:
            host_e.insert(0, pre_host)

        # Username
        ctk.CTkLabel(form, text="Username",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(2, 1))
        user_e = ctk.CTkEntry(
            form, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI, placeholder_text="username")
        user_e.pack(fill="x", pady=(0, 6))
        user_e.insert(0, entry.get("username", ""))


        # Port
        port_row = ctk.CTkFrame(form, fg_color="transparent")
        port_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(port_row, text="Port",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(side="left")
        port_e = ctk.CTkEntry(
            port_row, width=80, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI)
        port_e.pack(side="left", padx=(10, 0))
        port_e.insert(0, str(self._extract_port(
            entry.get("url", ""), 3389)))

        # Error label
        err = ctk.CTkLabel(form, text="", text_color=RED,
                            font=ctk.CTkFont(size=10), height=14)
        err.pack(fill="x", pady=(0, 2))

        # Info label
        ctk.CTkLabel(
            form, text="💡 Password will be copied to clipboard",
            font=ctk.CTkFont(size=9), text_color=TEXT_TERT).pack(fill="x")

        def connect():
            host = host_e.get().strip()
            port_str = port_e.get().strip()

            if not host:
                err.configure(text="⚠️ Host / IP is required")
                return
            try:
                port = int(port_str)
            except ValueError:
                err.configure(text="⚠️ Invalid port number")
                return

            # Stage password briefly (10s) so user can paste, then auto-clear
            self._copy_to_clipboard(entry.get("password", ""),
                                     force_clear_seconds=10)

            dlg.destroy()

            # Launch RDP — sanitize to prevent injection
            host = self._sanitize_shell_arg(host)
            try:
                rdp_target = f"{host}:{port}" if port != 3389 else host
                subprocess.Popen(["mstsc", f"/v:{rdp_target}"])
            except OSError as exc:
                log.warning("Failed to launch RDP: %s", exc)

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkButton(
            btn_row, text="Cancel", width=90, height=36,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
            command=dlg.destroy).pack(side="left")
        connect_btn = ctk.CTkButton(
            btn_row, text="🖥️  Connect", height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white", corner_radius=8,
            command=connect)
        connect_btn.pack(side="right", fill="x", expand=True, padx=(8, 0))
        tip(connect_btn, "Start RDP session (password copied to clipboard)")
        dlg.bind("<Return>", lambda _e: connect())

        host_e.focus()

    # ─── Password Generator Dialog ───────────────────────────
    def _show_generator(self, target_entry):
        dlg = self._make_dialog("Password Generator", 380, 330)

        ctk.CTkLabel(
            dlg, text="🎲  Password Generator",
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
        tip(gen_entry,
            "Generated password — click Use This to apply it")

        sf = ctk.CTkFrame(frm, fg_color="transparent")
        sf.pack(fill="x", pady=(0, 8))
        sb = ctk.CTkProgressBar(sf, height=4, corner_radius=2,
                                  fg_color=BG_TERT, progress_color=GREEN)
        sb.pack(side="left", fill="x", expand=True)
        sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                            text_color=GREEN)
        sl.pack(side="left", padx=(6, 0))

        lv = ctk.IntVar(value=_gl)
        uv = ctk.BooleanVar(value=self.settings.get("gen_upper", True))
        lov = ctk.BooleanVar(value=self.settings.get("gen_lower", True))
        dv = ctk.BooleanVar(value=self.settings.get("gen_digits", True))
        sv = ctk.BooleanVar(value=self.settings.get("gen_symbols", True))

        lf = ctk.CTkFrame(frm, fg_color="transparent")
        lf.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(lf, text="Length:",
                      font=ctk.CTkFont(size=11),
                      text_color=TEXT_SEC).pack(side="left")
        ll = ctk.CTkLabel(lf, text=str(_gl),
                            font=ctk.CTkFont(size=11, weight="bold"),
                            text_color=TEXT_PRI, width=28)
        ll.pack(side="right")

        def regen(*_):
            pw = generate_password(lv.get(), uv.get(), lov.get(),
                                    dv.get(), sv.get())
            gen_var.set(pw)
            s, l, c = password_strength(pw)
            sb.set(s / 4)
            sb.configure(progress_color=c)
            sl.configure(text=l, text_color=c)

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
        for txt, var, desc in [
            ("ABC", uv, "Include uppercase letters"),
            ("abc", lov, "Include lowercase letters"),
            ("123", dv, "Include digits"),
            ("#$%", sv, "Include special characters"),
        ]:
            chk = ctk.CTkCheckBox(
                cf, text=txt, variable=var,
                font=ctk.CTkFont(size=11),
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                command=regen)
            chk.pack(side="left", padx=(0, 10))
            tip(chk, desc)

        bf = ctk.CTkFrame(frm, fg_color="transparent")
        bf.pack(fill="x")
        regen_btn = ctk.CTkButton(
            bf, text="🔄  Regenerate", height=32,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=TEXT_QUAT, corner_radius=8, command=regen)
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

    # ─── Add / Edit Entry Dialog ─────────────────────────────
    def show_entry_dialog(self, entry=None):
        is_edit = entry is not None
        dlg = self._make_dialog(
            "Edit Password" if is_edit else "New Password", 420, 540)

        ctk.CTkLabel(
            dlg,
            text="✏️  Edit Password" if is_edit else "＋  New Password",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(8, 4))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                         scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 0))

        # IDENTITY
        g1 = ios_group(scroll, "Identity", compact=True)
        title_val = entry.get("title", "") if is_edit else ""
        title_e = ios_field(g1, "Title", idx=0, value=title_val,
                             height=30)
        cats = self.data.get("categories", ["General"])

        cat_val = (entry.get("category", cats[0] if cats else "")
                   if is_edit else (cats[0] if cats else ""))
        cat_cb = ios_combo(g1, "Category", cats, cat_val, idx=1)
        url_val = entry.get("url", "") if is_edit else ""
        url_e = ios_field(g1, "URL", idx=2, value=url_val,
                           height=30, placeholder="https://example.com")

        # CREDENTIALS
        g2 = ios_group(scroll, "Credentials", compact=True)
        user_val = entry.get("username", "") if is_edit else ""
        user_e = ios_field(g2, "Username", idx=0, value=user_val,
                            height=30)

        ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
        pw_row = ctk.CTkFrame(g2, fg_color="transparent")
        pw_row.pack(fill="x", padx=12, pady=(2, 3))
        ctk.CTkLabel(pw_row, text="Password",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, width=72,
                      anchor="w").pack(side="left")
        pass_e = ctk.CTkEntry(
            pw_row, height=30, show="●",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=6,
            text_color=TEXT_PRI)
        pass_e.pack(side="left", fill="x", expand=True, padx=(4, 4))
        if is_edit:
            pass_e.insert(0, entry.get("password", ""))
        gen_btn = ctk.CTkButton(
            pw_row, text="🎲", width=28, height=28,
            font=ctk.CTkFont(size=13),
            fg_color=GREEN, hover_color=GREEN_HOVER, corner_radius=6,
            text_color=BG,
            command=lambda: self._show_generator(pass_e))
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
            pw_row, text="👁", width=28, height=28,
            font=ctk.CTkFont(size=12), fg_color="transparent",
            hover_color=BG_TERT, corner_radius=6,
            text_color=TEXT_SEC, command=toggle_pass)
        eye_btn.pack(side="right", padx=(0, 2))
        tip(eye_btn, "Show / hide password")

        # Strength bar
        sf = ctk.CTkFrame(scroll, fg_color="transparent")
        sf.pack(fill="x", padx=26, pady=(0, 2))
        str_bar = ctk.CTkProgressBar(
            sf, height=3, corner_radius=2,
            fg_color=BG_TERT, progress_color=TEXT_QUAT)
        str_bar.pack(side="left", fill="x", expand=True)
        str_bar.set(0)
        str_lbl = ctk.CTkLabel(sf, text="",
                                font=ctk.CTkFont(size=9),
                                text_color=TEXT_QUAT)
        str_lbl.pack(side="left", padx=(6, 0))
        tip(str_bar, "Password strength indicator")

        # Duplicate warning label
        dup_lbl = ctk.CTkLabel(scroll, text="",
                                font=ctk.CTkFont(size=9),
                                text_color=ORANGE, height=12)
        dup_lbl.pack(fill="x", padx=26, pady=(0, 2))

        _dup_timer = [None]          # debounce handle
        # Pre-build hash set for O(1) duplicate lookups
        _pw_hash_map: dict[str, str] = {}
        _own_id = entry.get("id") if is_edit else None
        for oe in self.data["entries"]:
            if oe.get("id") == _own_id:
                continue
            op = oe.get("password", "")
            if op:
                _pw_hash_map[hashlib.sha256(
                    op.encode()).hexdigest()] = oe.get("title", "?")

        def _check_dup():
            """Duplicate check (runs after debounce delay)."""
            pw = pass_e.get()
            if pw:
                h = hashlib.sha256(pw.encode()).hexdigest()
                dupe_title = _pw_hash_map.get(h)
                if dupe_title:
                    dup_lbl.configure(
                        text=f"⚠️ Same password used in "
                             f"'{dupe_title}'")
                    return
            dup_lbl.configure(text="")

        def upd_str(e=None):
            pw = pass_e.get()
            s, l, c = password_strength(pw)
            str_bar.set(s / 4)
            str_bar.configure(progress_color=c)
            str_lbl.configure(text=l, text_color=c)
            # Debounced duplicate check (300ms)
            if _dup_timer[0]:
                dlg.after_cancel(_dup_timer[0])
            _dup_timer[0] = dlg.after(300, _check_dup)

        pass_e.bind("<KeyRelease>", upd_str)
        if is_edit:
            upd_str()

        # COLOR picker
        g_color = ios_group(scroll, "Color", compact=True)
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
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="white",
                command=lambda k=ckey: _select_color(k))
            b.pack(side="left", padx=2)
            color_btns[ckey] = b
            tip(b, f"{info['label']} card color")

        def _select_color(k):
            current_color.set(k)
            for ck, cb in color_btns.items():
                cb.configure(text="✓" if ck == k else "")

        # NOTES
        g3 = ios_group(scroll, "Notes", compact=True)
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
            url_v = url_e.get().strip()
            now_iso = datetime.datetime.now().isoformat()

            if is_edit:
                entry.update(title=t, username=u, password=p,
                              url=url_v, category=c, notes=n,
                              color=col, modified_at=now_iso)
            else:
                self.data["entries"].append({
                    "id": str(uuid.uuid4()), "title": t,
                    "username": u, "password": p, "url": url_v,
                    "category": c, "notes": n, "color": col,
                    "pinned": False, "created_at": now_iso,
                    "modified_at": now_iso,
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
        dlg.bind("<Control-Return>", lambda _e: save())
        title_e.focus()

    # ─── Delete Confirm (→ Recycle Bin) ──────────────────────
    def confirm_delete(self, entry):

        dlg = self._make_dialog("Delete", 360, 175)

        ctk.CTkLabel(dlg, text="⚠️  Move to Recycle Bin?",
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(20, 4))
        ctk.CTkLabel(
            dlg,
            text=f'Delete "{entry.get("title", "")}"?\n'
                 f'You can restore it from the Recycle Bin.',
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC, justify="center").pack(pady=(0, 14))
        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=24)

        def do_del():

            eid = entry.get("id")
            # Move to trash
            trash_entry = dict(entry)
            trash_entry["deleted_at"] = datetime.datetime.now().isoformat()
            self.data.setdefault("trash", []).append(trash_entry)
            # Remove from entries
            if eid:
                self.data["entries"] = [
                    e for e in self.data["entries"]
                    if e.get("id") != eid]
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
            width=140, height=36, font=ctk.CTkFont(size=13),
            corner_radius=10, command=do_del).pack(side="left", padx=4)
        ctk.CTkButton(
            bf, text="Cancel", fg_color=BG_TERT,
            hover_color=CARD_HOVER, width=140, height=36,
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=dlg.destroy).pack(side="right", padx=4)
        dlg.bind("<Return>", lambda _e: do_del())

    # ─── Add Category ────────────────────────────────────────
    def show_add_cat_dialog(self):

        dlg = self._make_dialog("New Category", 350, 185)

        ctk.CTkLabel(dlg, text="📁  New Category",
                      font=ctk.CTkFont(family="Segoe UI", size=15,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 10))
        frm = ctk.CTkFrame(dlg, fg_color="transparent")

        frm.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        g = ios_group(frm)
        cat_e = ios_field(g, "Name", idx=0,
                           placeholder="Category name")
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

    # ─── Export Dialog ───────────────────────────────────────
    def show_export_dialog(self):
        dlg = self._make_dialog("Export Data", 420, 280)

        ctk.CTkLabel(dlg, text="📤  Export Data",
                      font=ctk.CTkFont(family="Segoe UI", size=16,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(16, 4))

        # Warning
        warn = ctk.CTkFrame(dlg, fg_color="#3a2a20", corner_radius=10)
        warn.pack(fill="x", padx=20, pady=(8, 12))
        ctk.CTkLabel(warn,
                      text="⚠️  The exported file will contain all your\n"
                           "passwords in PLAIN TEXT. Keep it secure!",
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=ORANGE, justify="center").pack(
            padx=12, pady=8)

        total = len(self.data.get("entries", []))
        ctk.CTkLabel(dlg,
                      text=f"📊  {total} entries will be exported",
                      font=ctk.CTkFont(size=12),
                      text_color=TEXT_SEC).pack(pady=(0, 12))

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 8))

        def do_export_csv():
            path = tkfiledialog.asksaveasfilename(
                parent=dlg, defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile="passwords_export.csv")
            if path:
                export_csv(self.data["entries"], path)
                dlg.destroy()

        def do_export_xlsx():
            if not HAS_OPENPYXL:
                ctk.CTkLabel(dlg, text="⚠️ openpyxl not installed",
                              text_color=RED,
                              font=ctk.CTkFont(size=11)).pack()
                return
            path = tkfiledialog.asksaveasfilename(
                parent=dlg, defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                initialfile="passwords_export.xlsx")
            if path:
                export_excel(self.data["entries"], path)
                dlg.destroy()

        ctk.CTkButton(
            bf, text="📄  Export CSV", height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=10, command=do_export_csv).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        tip_text = "Export to Excel (.xlsx)"
        xlsx_btn = ctk.CTkButton(
            bf, text="📊  Export Excel", height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=10, command=do_export_xlsx)
        xlsx_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
        if not HAS_OPENPYXL:
            xlsx_btn.configure(state="disabled", fg_color=BG_TERT)
            tip_text += " (install openpyxl)"
        tip(xlsx_btn, tip_text)

        ctk.CTkButton(
            dlg, text="Cancel", height=32, width=100,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=8,
            command=dlg.destroy).pack(pady=(0, 12))

    # ─── Import Dialog ───────────────────────────────────────
    def show_import_dialog(self):
        dlg = self._make_dialog("Import Data", 420, 340)

        ctk.CTkLabel(dlg, text="📥  Import Data",
                      font=ctk.CTkFont(family="Segoe UI", size=16,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(16, 8))

        ctk.CTkLabel(dlg,
                      text="Select a CSV or Excel file to import.\n"
                           "Columns: Title, Username, Password, "
                           "URL, Category, Notes",
                      font=ctk.CTkFont(size=11),
                      text_color=TEXT_SEC, justify="center").pack(
            pady=(0, 10))

        info_lbl = ctk.CTkLabel(dlg, text="",
                                  font=ctk.CTkFont(size=12),
                                  text_color=TEXT_PRI)
        info_lbl.pack(pady=(0, 8))

        status_lbl = ctk.CTkLabel(dlg, text="",
                                    font=ctk.CTkFont(size=11),
                                    text_color=GREEN)
        status_lbl.pack(pady=(0, 8))

        import_data = {"entries": []}

        def browse():
            ftypes = [("CSV files", "*.csv")]
            if HAS_OPENPYXL:
                ftypes.insert(0, ("Excel files", "*.xlsx"))
            ftypes.append(("All files", "*.*"))
            path = tkfiledialog.askopenfilename(
                parent=dlg, filetypes=ftypes)
            if not path:
                return
            try:
                if path.endswith(".xlsx"):
                    entries = import_excel(path)
                else:
                    entries = import_csv(path)
                import_data["entries"] = entries
                # Check duplicates
                existing_titles = {
                    (e.get("title", ""), e.get("username", ""))
                    for e in self.data["entries"]}
                new = [e for e in entries
                       if (e["title"], e["username"])
                       not in existing_titles]
                dup = len(entries) - len(new)
                info_lbl.configure(
                    text=f"📊  Found {len(entries)} entries  |  "
                         f"New: {len(new)}  |  Duplicates: {dup}")
                import_data["new_only"] = new
                import_data["all"] = entries
            except (OSError, ValueError, KeyError, csv.Error) as ex:
                info_lbl.configure(text=f"⚠️ Error: {ex}")

        ctk.CTkButton(
            dlg, text="📂  Browse File...", height=36, width=200,
            font=ctk.CTkFont(size=13), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=10,
            command=browse).pack(pady=(0, 10))

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 8))

        def do_import(skip_dup):
            entries = (import_data.get("new_only", [])
                       if skip_dup
                       else import_data.get("all", []))
            if not entries:
                status_lbl.configure(
                    text="⚠️ No entries to import",
                    text_color=ORANGE)
                return
            # Add categories
            existing_cats = set(self.data.get("categories", []))
            for e in entries:
                cat = e.get("category", "General")
                if cat and cat not in existing_cats:
                    self.data["categories"].append(cat)
                    existing_cats.add(cat)
            self.data["entries"].extend(entries)
            save_data(self.data, self.key)
            self.refresh_categories()
            self.refresh_entries()
            dlg.destroy()

        ctk.CTkButton(
            bf, text="Import (Skip Dups)", height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
            corner_radius=10,
            command=lambda: do_import(True)).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            bf, text="Import All", height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=10,
            command=lambda: do_import(False)).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

        ctk.CTkButton(
            dlg, text="Cancel", height=32, width=100,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=8,
            command=dlg.destroy).pack(pady=(0, 12))

    # ─── Recycle Bin Dialog ──────────────────────────────────
    def show_trash_dialog(self):
        dlg = self._make_dialog("Recycle Bin", 460, 480)

        trash = self.data.get("trash", [])
        ctk.CTkLabel(
            dlg,
            text=f"🗑️  Recycle Bin  ({len(trash)} items)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(14, 2))
        ctk.CTkLabel(
            dlg,
            text=f"Items are automatically deleted after {TRASH_DAYS} days",
            font=ctk.CTkFont(size=10), text_color=TEXT_TERT).pack(
            pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                         scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def refresh_list():
            for w in scroll.winfo_children():
                w.destroy()
            trash_items = self.data.get("trash", [])
            if not trash_items:
                ctk.CTkLabel(scroll, text="🗑️  Empty",
                              font=ctk.CTkFont(size=14),
                              text_color=TEXT_TERT).pack(pady=60)
                return
            for item in trash_items:
                _trash_card(item)

        def _trash_card(item):
            card = ctk.CTkFrame(scroll, fg_color=BG_SEC,
                                  corner_radius=10)
            card.pack(fill="x", pady=3, padx=2)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=8)

            emoji = cat_emoji(item.get("category", ""))
            ctk.CTkLabel(
                inner,
                text=f"{emoji}  {item.get('title', '')}",
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                  weight="bold"),
                text_color=TEXT_PRI, anchor="w").pack(
                fill="x")

            # Deleted date
            del_at = item.get("deleted_at", "")
            age_t, _ = password_age_text(del_at)
            ctk.CTkLabel(
                inner,
                text=f"🗑️ Deleted {age_t}" if age_t else "",
                font=ctk.CTkFont(size=10),
                text_color=TEXT_TERT).pack(
                fill="x", pady=(2, 4))

            brow = ctk.CTkFrame(inner, fg_color="transparent")
            brow.pack(fill="x")

            def restore(it=item):
                # Remove from trash, add back to entries
                it_copy = dict(it)
                it_copy.pop("deleted_at", None)
                it_copy["modified_at"] = (
                    datetime.datetime.now().isoformat())
                self.data["entries"].append(it_copy)
                self.data["trash"] = [
                    t for t in self.data["trash"]
                    if t.get("id") != it.get("id")]
                save_data(self.data, self.key)
                self.refresh_categories()
                self.refresh_entries()
                refresh_list()

            def perm_del(it=item):
                # Confirm before destroying — Delete Forever is irreversible.
                confirm = ctk.CTkToplevel(dlg)
                confirm.title("Delete Forever")
                confirm.geometry("340x180")
                confirm.resizable(False, False)
                confirm.configure(fg_color=BG)
                confirm.transient(dlg)
                confirm.grab_set()
                self._center(confirm, 340, 180)
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
                    self.data["trash"] = [
                        t for t in self.data["trash"]
                        if t.get("id") != it.get("id")]
                    save_data(self.data, self.key)
                    confirm.destroy()
                    refresh_list()

                ctk.CTkButton(
                    cbf, text="Delete", fg_color=RED,
                    hover_color=RED_HOVER, width=130, height=34,
                    font=ctk.CTkFont(size=13), corner_radius=10,
                    command=do_perm).pack(side="left", padx=4)
                ctk.CTkButton(
                    cbf, text="Cancel", fg_color=BG_TERT,
                    hover_color=CARD_HOVER, width=130, height=34,
                    font=ctk.CTkFont(size=13), corner_radius=10,
                    command=confirm.destroy).pack(side="right", padx=4)
                confirm.bind("<Return>", lambda _e: do_perm())

            r_btn = ctk.CTkButton(
                brow, text="♻️ Restore", height=26,
                font=ctk.CTkFont(size=10), fg_color=GREEN,
                hover_color=GREEN_HOVER, text_color=BG,
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

        refresh_list()

        # Bottom buttons
        bot = ctk.CTkFrame(dlg, fg_color="transparent")
        bot.pack(fill="x", padx=14, pady=(0, 12))

        def empty_trash():
            # Confirmation dialog before emptying
            confirm = ctk.CTkToplevel(dlg)
            confirm.title("Empty Trash")
            confirm.geometry("340x170")
            confirm.resizable(False, False)
            confirm.configure(fg_color=BG)
            confirm.transient(dlg)
            confirm.grab_set()
            self._center(confirm, 340, 170)

            ctk.CTkLabel(confirm, text="⚠️  Empty Recycle Bin?",
                          font=ctk.CTkFont(family="Segoe UI", size=16,
                                            weight="bold"),
                          text_color=TEXT_PRI).pack(pady=(18, 4))
            ctk.CTkLabel(
                confirm,
                text=f"Permanently delete all {len(self.data.get('trash', []))} "
                     f"items?\nThis action cannot be undone.",
                font=ctk.CTkFont(size=12),
                text_color=TEXT_SEC, justify="center").pack(pady=(0, 14))

            cbf = ctk.CTkFrame(confirm, fg_color="transparent")
            cbf.pack(fill="x", padx=24)

            def do_empty():
                self.data["trash"] = []
                save_data(self.data, self.key)
                log.info("Recycle bin emptied.")
                confirm.destroy()
                refresh_list()

            ctk.CTkButton(
                cbf, text="Delete All", fg_color=RED,
                hover_color=RED_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=do_empty).pack(side="left", padx=4)
            ctk.CTkButton(
                cbf, text="Cancel", fg_color=BG_TERT,
                hover_color=CARD_HOVER, width=130, height=34,
                font=ctk.CTkFont(size=13), corner_radius=10,
                command=confirm.destroy).pack(side="right", padx=4)

        if trash:
            et_btn = ctk.CTkButton(
                bot, text="🗑️  Empty Trash", height=34,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=RED, hover_color=RED_HOVER,
                corner_radius=10, command=empty_trash)
            et_btn.pack(side="left", fill="x", expand=True,
                         padx=(0, 4))
            tip(et_btn, "Permanently delete all items in trash")

        ctk.CTkButton(
            bot, text="Close", height=34,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=10,
            command=dlg.destroy).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    # ─── Security Dashboard ──────────────────────────────────
    def show_security_dashboard(self):
        dlg = self._make_dialog("Security Dashboard", 480, 560)

        entries = self.data.get("entries", [])
        score, stats = calculate_security_score(entries)

        ctk.CTkLabel(dlg, text="🛡️  Security Dashboard",
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(14, 8))

        # Score circle
        score_color = GREEN if score >= 70 else (ORANGE if score >= 40
                                                   else RED)
        sc_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        sc_frame.pack(pady=(0, 8))
        ctk.CTkLabel(sc_frame,
                      text=f"🏆  {score}",
                      font=ctk.CTkFont(family="Segoe UI", size=44,
                                        weight="bold"),
                      text_color=score_color).pack(side="left")
        ctk.CTkLabel(sc_frame, text="/ 100",
                      font=ctk.CTkFont(size=16),
                      text_color=TEXT_SEC).pack(
            side="left", padx=(4, 0), pady=(14, 0))

        # Progress bar
        pb = ctk.CTkProgressBar(dlg, width=300, height=8,
                                  corner_radius=4,
                                  fg_color=BG_TERT,
                                  progress_color=score_color)
        pb.pack(pady=(0, 14))
        pb.set(score / 100)
        tip(pb, f"Your security score: {score}/100")

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                         scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        # Overview group
        g = ios_group(scroll, "Overview")

        def stat_row(grp, icon, label, value, color, idx=0):
            if idx > 0:
                ctk.CTkFrame(grp, height=1,
                              fg_color=SEPARATOR).pack(
                    fill="x", padx=(46, 0))
            row = ctk.CTkFrame(grp, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(row, text=f"{icon}  {label}",
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          text_color=TEXT_SEC, anchor="w").pack(
                side="left")
            ctk.CTkLabel(row, text=str(value),
                          font=ctk.CTkFont(family="Segoe UI", size=14,
                                            weight="bold"),
                          text_color=color, anchor="e").pack(
                side="right")

        stat_row(g, "📊", "Total Entries",
                  stats["total"], TEXT_PRI, 0)
        stat_row(g, "💪", "Strong Passwords",
                  stats["strong"], GREEN, 1)
        stat_row(g, "⚖️", "Fair Passwords",
                  stats["fair"], ORANGE, 2)
        stat_row(g, "⚠️", "Weak Passwords",
                  stats["weak"], RED, 3)
        stat_row(g, "🔁", "Duplicate Passwords",
                  stats["duplicates"], ORANGE, 4)
        stat_row(g, "⏰", f"Old (>{PASSWORD_AGE_WARNING}d)",
                  stats["old"], ORANGE, 5)

        # Recommendations
        recs = []
        if stats["weak"] > 0:
            recs.append(
                f"⚠️  {stats['weak']} weak password(s) — "
                f"update them for better security")
        if stats["duplicates"] > 0:
            recs.append(
                f"🔁  {stats['duplicates']} reused password(s) — "
                f"use unique passwords per account")
        if stats["old"] > 0:
            recs.append(
                f"⏰  {stats['old']} password(s) older than "
                f"{PASSWORD_AGE_WARNING} days — consider updating")
        if not recs:
            recs.append("✅  Great job! Your vault is secure!")

        g2 = ios_group(scroll, "Recommendations")
        for i, rec in enumerate(recs):
            if i > 0:
                ctk.CTkFrame(g2, height=1,
                              fg_color=SEPARATOR).pack(
                    fill="x", padx=(16, 0))
            ctk.CTkLabel(g2, text=rec,
                          font=ctk.CTkFont(family="Segoe UI", size=11),
                          text_color=TEXT_PRI, anchor="w",
                          wraplength=380, justify="left").pack(
                fill="x", padx=12, pady=5)

        # Breach check section
        g3 = ios_group(scroll, "Breach Check")
        breach_lbl = ctk.CTkLabel(
            g3,
            text="Check if your passwords appear in known\n"
                 "data breaches (via Have I Been Pwned).",
            font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
            justify="center")
        breach_lbl.pack(padx=12, pady=(8, 4))

        breach_result = ctk.CTkLabel(
            g3, text="", font=ctk.CTkFont(size=11),
            text_color=TEXT_PRI, wraplength=380, justify="left")
        breach_result.pack(padx=12, pady=(0, 8))

        def start_breach():
            if not entries:
                breach_result.configure(
                    text="No entries to check.", text_color=TEXT_SEC)
                return
            breach_btn.configure(state="disabled",
                                  text="⏳ Checking...")
            breach_result.configure(
                text="Checking passwords against HIBP database...",
                text_color=TEXT_SEC)

            def on_done(results):
                def _update():
                    breached = {eid: c for eid, c in results.items()
                                if c > 0}
                    errors = sum(1 for c in results.values() if c < 0)
                    if breached:
                        names = []
                        for e in entries:
                            if e.get("id") in breached:
                                names.append(
                                    f"  ⛔ {e.get('title', '?')} "
                                    f"({breached[e['id']]:,}x)")
                        txt = (f"🚨 {len(breached)} password(s) "
                               f"found in breaches!\n"
                               + "\n".join(names))
                        breach_result.configure(
                            text=txt, text_color=RED)
                    else:
                        txt = "✅ No passwords found in breaches!"
                        if errors:
                            txt += (f"\n⚠️ {errors} could not "
                                    f"be checked (network error)")
                        breach_result.configure(
                            text=txt, text_color=GREEN)
                    breach_btn.configure(
                        state="normal", text="🔍  Check Breaches")

                self.root.after(0, _update)

            check_hibp_batch(entries, None, on_done)

        breach_btn = ctk.CTkButton(
            g3, text="🔍  Check Breaches", height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PURPLE, hover_color="#a04ad0",
            corner_radius=8, command=start_breach)
        breach_btn.pack(padx=12, pady=(0, 10))
        tip(breach_btn,
            "Check all passwords against the HIBP breach database "
            "(uses k-anonymity — your passwords are NOT sent)")

        # Close
        ctk.CTkButton(
            dlg, text="Close", height=36, width=140,
            font=ctk.CTkFont(size=13), fg_color=BG_TERT,
            hover_color=CARD_HOVER, corner_radius=10,
            command=dlg.destroy).pack(pady=(0, 12))

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
            except tk.TclError:
                pass
        self.root.deiconify()
        self.root.state("normal")
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        
        self.root.after(
            300, lambda: self.root.attributes("-topmost", False))
        if self.floating_widget:
            self.floating_widget.withdraw()

    def quit_app(self):

        log.info("Application exiting.")
        try:
            if self._clipboard_timer:
                self.root.after_cancel(self._clipboard_timer)
            if self._idle_timer:
                self.root.after_cancel(self._idle_timer)
        except tk.TclError:
            pass
        if self.mini_vault:
            try:
                self.mini_vault.destroy()
            except tk.TclError:
                pass
        if self.floating_widget:
            try:
                self.floating_widget.destroy()
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        sys.exit(0)

    def _center(self, dlg, w, h):
        dlg.update_idletasks()

        cx = (self.root.winfo_x()
              + (self.root.winfo_width() // 2) - (w // 2))
        cy = (self.root.winfo_y()
              + (self.root.winfo_height() // 2) - (h // 2))
        dlg.geometry(f"{w}x{h}+{cx}+{cy}")

    def _make_dialog(self, title: str, w: int, h: int) -> ctk.CTkToplevel:
        """Create a standard centered modal dialog."""
        self._reset_idle()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.geometry(f"{w}x{h}")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center(dlg, w, h)
        # Esc closes the dialog. Individual dialogs may bind <Return> to
        # their primary action (Save/Connect/Confirm).
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        return dlg

    def _copy_to_clipboard(self, text: str, btn=None,
                            force_clear_seconds: int | None = None) -> None:
        """Copy *text* to clipboard with auto-clear scheduling.

        If *btn* is provided, flash a '✅ Done!' confirmation on it.
        If *force_clear_seconds* is set, override the user setting (used by
        SSH/RDP flows that briefly stage the password for paste).
        """
        pyperclip.copy(text)
        if btn:
            orig = btn.cget("text")
            orig_fg = btn.cget("fg_color")
            btn.configure(text="✅ Done!", fg_color=GREEN)
            self.root.after(
                1000, lambda: safe_cfg(btn, orig, orig_fg))
        clear_sec = (force_clear_seconds
                     if force_clear_seconds is not None
                     else self.settings.get("clipboard_clear_seconds", 30))
        if clear_sec > 0:
            if self._clipboard_timer:
                self.root.after_cancel(self._clipboard_timer)
            self._clipboard_timer = self.root.after(
                clear_sec * 1000, self._clear_clipboard)

    def run(self):

        if (self.settings.get("start_minimized", False)
                and os.path.exists(DATA_FILE)):
            self.root.after(200, self.minimize_to_widget)
        self.root.mainloop()


if __name__ == "__main__":
    PasswordVault().run()

