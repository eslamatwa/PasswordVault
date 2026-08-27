"""

🔐 Password Vault - Modern password manager for Windows (Apple Dark Style)

This is the main entry point. Utility modules live under ``password_vault/``.
"""


from __future__ import annotations

import customtkinter as ctk
import tkinter as tk

import datetime
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser

import pyperclip

from cryptography.fernet import InvalidToken

from password_vault import instance_lock
from password_vault.i18n import (
    LANGUAGE_VALUES, anchor_end, anchor_start, justify_end, justify_start,
    label_for, pad, set_language, side_end, side_start, t, value_for,
)
from password_vault.theme import (
    CARD_COLORS, BG, BG_SEC, BG_TERT, SEPARATOR,
    ACCENT, ACCENT_HOVER, GREEN, GREEN_HOVER, RED, RED_HOVER,
    ORANGE, YELLOW, TEAL,
    TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT, TEXT_ON_ACCENT, TEXT_ON_GREEN,
    BADGE_BG, INPUT_BG, CARD_HOVER, SIDEBAR_BG, SIDEBAR_SEL,
    cat_emoji, menu_style, resolve,
)
from password_vault.settings import (
    AUTO_LOCK_MINUTES, MAX_LOGIN_ATTEMPTS, LOCKOUT_SECONDS,
    MAX_LOCKOUT_HORIZON, THEME_MODES,
    load_settings, save_settings,
)
from password_vault.crypto import (
    DATA_FILE, APP_DIR,
    get_or_create_salt, derive_key, save_data, load_data,
)
from password_vault.security import (
    password_strength, password_age_text, safe_url, password_hash,
)
from password_vault.ui.widgets import (
    tip, ios_group, ios_field, ios_combo, make_search_bar, safe_cfg,
    bind_right_click_recursive, add_color_strip, sort_entries_pinned_first,
    ui_font, elide, filter_entries, dialog_header, button_row,
)
from password_vault.ui.mini_vault import MiniVault
from password_vault.ui.floating import FloatingWidget

# ─── Logging ──────────────────────────────────────────────────
log = logging.getLogger("PasswordVault")

# How many entry cards to build per render pass. Tk has no virtualized list,
# so an unbounded vault would create thousands of widgets on every keystroke.
ENTRIES_PAGE_SIZE = 60

# Minimum gap between idle-timer reschedules. <Motion> fires dozens of times
# per second; without this every mouse move cancels and re-arms a Tk timer.
IDLE_RESET_THROTTLE_SEC = 5

# Delay before a low-value change (pin toggle) is flushed to disk. Saving
# re-encrypts the whole vault, so rapid toggles should coalesce.
SAVE_DEBOUNCE_MS = 800

# Fixed-width placeholder for a hidden password, so the rendered width says
# nothing about the real length.
PASSWORD_MASK = "●" * 10

# Card titles longer than this are elided; the full text moves to a tooltip.
TITLE_MAX_CHARS = 38

# Categories whose entries always offer SSH / RDP actions.
REMOTE_CATEGORIES = frozenset({"server", "vpn", "ssh", "rdp", "database"})

# Windows virtual-key codes for the Ctrl shortcuts, so they keep working
# under a non-Latin keyboard layout where the keysym is localized.
_SHORTCUT_KEYCODES = {78: "n", 70: "f", 76: "l", 69: "e", 73: "i"}


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
        self._last_idle_reset = 0.0
        self._main_frame = None
        self._clipboard_timer = None
        self._clipboard_digest = None
        self._search_bar = None
        self._search_after_id = None
        self._visible_limit = ENTRIES_PAGE_SIZE
        self._save_timer = None
        self._save_pending = False
        self._shortcuts_bound = False
        # True while the unlock worker is deriving the key, so a second
        # Enter cannot start a parallel derivation against the same salt.
        self._unlocking = False
        # One dialog per run of failed deferred saves, not one per
        # flush: a read-only disk retries on every lock and minimize.
        self._save_failure_reported = False
        self.unlock_btn = None
        self._unlock_btn_text = ""
        # Open modal dialogs, innermost last: the grab has to be handed back
        # when a nested dialog closes.
        self._grab_stack: list = []

        self.settings = load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "Dark"))
        # Language before any widget is built: anchors, pack sides and
        # padding are all fixed at creation time, so the direction has to
        # be known first.
        set_language(self.settings.get("language", "English"))
        self._restore_lockout_state()

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
        self._bind_activity_events()
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
            self.root.bind_all("<Key>", self._on_shortcut_keycode, add="+")

        # ── Right-click context menu ──────────────────────────
        def _ctx_menu(event):
            w = event.widget
            if not isinstance(w, (tk.Entry, tk.Text)):
                return

            # Give focus so selection is visible
            w.focus_set()

            menu = tk.Menu(w, tearoff=0, **menu_style())

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
                label=t("✂️  Cut"),
                command=lambda: w.event_generate("<<Cut>>"),
                state="normal" if has_sel else "disabled")
            menu.add_command(
                label=t("📋  Copy"),
                command=lambda: w.event_generate("<<Copy>>"),
                state="normal" if has_sel else "disabled")
            menu.add_command(
                label=t("📄  Paste"),
                command=lambda: w.event_generate("<<Paste>>"),
                state="normal" if has_clip else "disabled")
            menu.add_separator()
            menu.add_command(
                label=t("🔤  Select All"),
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

    # ─── Brute-Force State ───────────────────────────────────
    def _restore_lockout_state(self):
        """Reload the failed-attempt streak and any pending lockout.

        Both used to live only in memory, so quitting and relaunching
        cleared the lockout and returned a full set of attempts — which
        made the limit advertised in Settings trivial to sit out.
        """
        self._failed_streak = self.settings.get("failed_streak", 0)
        stored = self.settings.get("lockout_until", 0)
        now = time.time()
        # A stored deadline is an absolute timestamp, so it is only
        # meaningful against the current clock. Anything beyond the longest
        # penalty this app issues came from a clock change, not from us.
        self._lockout_until = (stored
                               if now < stored <= now + MAX_LOCKOUT_HORIZON
                               else 0)

    def _persist_lockout_state(self):
        self.settings["failed_streak"] = self._failed_streak
        self.settings["lockout_until"] = int(self._lockout_until)
        save_settings(self.settings)

    # ─── Auto-Lock ───────────────────────────────────────────
    def _bind_activity_events(self):
        """Track user activity across every window, once per process.

        `bind_all` rather than `root.bind`: with root-only bindings the app
        saw no activity while the Mini Vault or a dialog had focus and
        locked under the user's hands. These bindings are never removed —
        unbinding would clear the shared "all" bindtag that also carries the
        clipboard key handler, and `_reset_idle` already ignores events
        while the vault is locked.
        """
        for ev in ("<Motion>", "<Key>", "<Button>", "<MouseWheel>"):
            self.root.bind_all(ev, self._reset_idle, add="+")

    def _start_idle_timer(self):
        self._reset_idle(force=True)

    def _reset_idle(self, event=None, force=False):
        """Re-arm the auto-lock timer.

        Throttled: activity within IDLE_RESET_THROTTLE_SEC of the last reset
        is ignored, which bounds the effective lock time to the configured
        interval plus that window. Pass *force* when the interval itself
        changed and the timer must be re-armed immediately.
        """
        if self.key is None:
            return
        now = time.time()
        if not force and now - self._last_idle_reset < IDLE_RESET_THROTTLE_SEC:
            return
        self._last_idle_reset = now
        if self._idle_timer:
            try:
                self.root.after_cancel(self._idle_timer)
            except (tk.TclError, ValueError):
                pass
            self._idle_timer = None
        mins = self.settings.get("auto_lock_minutes", AUTO_LOCK_MINUTES)
        if mins > 0:
            self._idle_timer = self.root.after(
                mins * 60 * 1000, self._auto_lock)

    # ─── Deferred Save ───────────────────────────────────────
    def _schedule_save(self):
        """Coalesce rapid low-value writes into a single re-encrypt.

        Always paired with _flush_pending_save() on lock, minimize and quit
        so a pending change can never be lost silently.
        """
        self._save_pending = True
        if self._save_timer:
            try:
                self.root.after_cancel(self._save_timer)
            except (tk.TclError, ValueError):
                pass
        self._save_timer = self.root.after(
            SAVE_DEBOUNCE_MS, self._flush_pending_save)

    def _flush_pending_save(self, notify: bool = True):
        if self._save_timer:
            try:
                self.root.after_cancel(self._save_timer)
            except (tk.TclError, ValueError):
                pass
            self._save_timer = None
        if not self._save_pending:
            return
        if self.data is None or self.key is None:
            self._save_pending = False
            return
        try:
            save_data(self.data, self.key)
        except (OSError, ValueError, TypeError) as exc:
            # Keep the change pending so the next flush (lock, minimize or
            # quit) retries it instead of dropping it.
            log.error("Deferred save failed: %s", exc, exc_info=True)
            # A silent retry told the user nothing: pinning an entry on a
            # full disk looked like it worked, and the only symptom was the
            # pin being gone at the next unlock. Reported once per run of
            # failures, so a read-only disk does not produce one dialog per
            # flush attempt, and never while quitting — the window is about
            # to go away and the dialog would only flash.
            if notify and not self._save_failure_reported:
                self._save_failure_reported = True
                self._alert(
                    t("Could not save"),
                    t("The vault file could not be written, so this change "
                      "is only in memory for now.\n\n{error}", error=exc))
            return
        self._save_pending = False
        self._save_failure_reported = False

    def _destroy_open_dialogs(self):
        """Close every open child window before the vault locks.

        Dialogs render plaintext passwords and hold their own references to
        the vault; leaving them up meant secrets stayed on screen after the
        lock and a later save from one of them hit a cleared key.

        The floating widget is kept on purpose: it carries no secrets and is
        the only way back into the app while the main window is hidden.
        """
        keep = self.floating_widget
        for child in list(self.root.winfo_children()):
            if not isinstance(child, tk.Toplevel):
                continue
            if keep is not None and child is keep:
                continue
            try:
                child.grab_release()
            except tk.TclError:
                pass
            try:
                child.destroy()
            except tk.TclError:
                pass

    def _auto_lock(self):
        if self.key is None:
            # Already locked — the login screen is up. Building a second
            # one over it would leave both frames placed on top of
            # each other.
            self._idle_timer = None
            return
        log.info("Vault auto-locked due to inactivity.")
        self._flush_pending_save()
        if self.mini_vault:
            try:
                self.mini_vault.destroy()
            except tk.TclError:
                pass
            self.mini_vault = None
        self._destroy_open_dialogs()
        # Python strings are immutable; GC may retain copies of sensitive
        # data after refs drop. There's no portable way to securely wipe
        # them. Just release references and let the GC reclaim.
        self.key = None
        self.data = None
        self._idle_timer = None
        self._unbind_shortcuts()
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


        ctk.CTkLabel(self.login_frame, text=t("Password Vault"),
                      font=ctk.CTkFont(family="Segoe UI", size=30,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(pady=(0, 4))

        is_new = not os.path.exists(DATA_FILE)

        ctk.CTkLabel(
            self.login_frame,
            text=(t("Create a master password") if is_new
                  else t("Enter your master password")),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SEC).pack(pady=(0, 24))

        pw_frame = ctk.CTkFrame(self.login_frame, fg_color="transparent")
        pw_frame.pack(pady=(0, 6))

        self.master_entry = ctk.CTkEntry(

            pw_frame, width=280, height=44,
            placeholder_text=t("Master Password"), show="●",
            font=ctk.CTkFont(family="Segoe UI", size=14), justify="center",
            fg_color=BG_SEC, border_color=BG_TERT, border_width=1,
            corner_radius=12, text_color=TEXT_PRI)
        self.master_entry.pack(side="left")
        self.master_entry.bind("<Return>", lambda e: self.unlock())

        tip(self.master_entry,
            t("Enter your master password to unlock the vault"))

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
        tip(eye_master, t("Show / hide password"))

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
                t("Shows how strong your password is"))

            self.confirm_entry = ctk.CTkEntry(

                self.login_frame, width=320, height=44,
                placeholder_text=t("Confirm Password"), show="●",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                justify="center", fg_color=BG_SEC,
                border_color=BG_TERT, border_width=1,
                corner_radius=12, text_color=TEXT_PRI)
            self.confirm_entry.pack(pady=(0, 10))
            self.confirm_entry.bind("<Return>", lambda e: self.unlock())

            tip(self.confirm_entry,
                t("Re-enter your password to confirm"))

        self._unlock_btn_text = (t("Unlock  🔓") if not is_new
                                 else t("Create Vault  🔐"))
        unlock_btn = ctk.CTkButton(
            self.login_frame,
            text=self._unlock_btn_text,
            width=320, height=46,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=12,

            command=self.unlock)
        self.unlock_btn = unlock_btn
        unlock_btn.pack(pady=(10, 0))
        tip(unlock_btn,
            t("Decrypt and open your vault") if not is_new
            else t("Create a new encrypted vault"))

        # Subtle "Restore from backup" link — useful both on first-run
        # (you have a backup from another machine) and when the user
        # forgot their master password.
        restore_btn = ctk.CTkButton(
            self.login_frame, text=t("🛟  Restore from backup"),
            width=220, height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", hover_color=BG_SEC,
            corner_radius=10, text_color=TEXT_SEC,
            command=self._show_login_restore_dialog)
        restore_btn.pack(pady=(8, 0))
        tip(restore_btn,
            t("Restore vault contents from an encrypted backup file"))

        self.master_entry.focus()

    def _show_login_restore_dialog(self):
        """Open the login-time restore flow (no current vault required)."""
        from password_vault.ui.dialogs import backup
        backup.show_restore_at_login(self)

    def _finish_unlock_after_restore(self):
        """Called by the login-restore flow after data is written and the
        new master key is set. Tear down the login screen and bring up
        the main UI."""
        self._login_attempts = 0
        self._failed_streak = 0
        self._lockout_until = 0
        self._persist_lockout_state()
        try:
            self.login_frame.destroy()
        except (AttributeError, tk.TclError):
            pass
        self.build_ui()
        self._start_idle_timer()
        self._bind_shortcuts()


    def _update_login_strength(self, event=None):
        s, lbl, c = password_strength(self.master_entry.get())
        self.strength_bar.set(s / 4)
        self.strength_bar.configure(progress_color=c)
        self.strength_label.configure(text=lbl, text_color=c)

    def _validate_master_password(self, pw):
        if len(pw) < 12:
            return t("⚠️ Too short (min 12 chars for master password)")
        if not any(c.isupper() for c in pw):
            return t("⚠️ Need at least one uppercase letter")
        if not any(c.islower() for c in pw):
            return t("⚠️ Need at least one lowercase letter")
        if not any(c.isdigit() for c in pw):
            return t("⚠️ Need at least one digit")
        score, _, _ = password_strength(pw)
        if score < 3:
            return t("⚠️ Master password is not strong enough")
        return None

    def unlock(self):

        if self._unlocking:
            return
        now = time.time()
        if now < self._lockout_until:
            remaining = int(self._lockout_until - now)
            self.error_label.configure(
                text=t("⚠️ Too many attempts. Wait {seconds}s",
                       seconds=remaining))
            return
        pw = self.master_entry.get()
        if not pw:
            self.error_label.configure(text=t("⚠️ Enter a password"))
            return


        is_new = not os.path.exists(DATA_FILE)
        if is_new:
            c = self.confirm_entry.get() if self.confirm_entry else ""
            if pw != c:

                self.error_label.configure(
                    text=t("⚠️ Passwords don't match"))
                return

            err = self._validate_master_password(pw)
            if err:
                self.error_label.configure(text=err)
                return


        # Deriving the key is ~300ms of deliberate PBKDF2 work and decrypting
        # follows it, so the whole thing goes to a worker: on the Tk thread
        # it froze the window at every single unlock, including the redraw
        # that would have shown the user their keypress landed.
        salt = get_or_create_salt()
        self._set_unlocking(True)

        def work():
            try:
                key = derive_key(pw, salt)
                data = load_data(key)
            except BaseException as exc:  # noqa: BLE001 - marshalled below
                self.root.after(0, lambda exc=exc: self._unlock_done(
                    is_new, None, None, exc))
                return
            self.root.after(0, lambda: self._unlock_done(
                is_new, key, data, None))

        threading.Thread(target=work, daemon=True).start()

    def _set_unlocking(self, busy: bool) -> None:
        """Show that the vault is being opened, and refuse a second submit."""
        self._unlocking = busy
        try:
            self.unlock_btn.configure(
                state="disabled" if busy else "normal",
                text=t("⏳  Unlocking…") if busy else self._unlock_btn_text)
            if busy:
                self.error_label.configure(text="")
        except (AttributeError, tk.TclError):
            pass

    def _unlock_done(self, is_new: bool, key, data, exc) -> None:
        """Back on the Tk thread with the result of the derivation."""
        try:
            if not self.error_label.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return
        self._set_unlocking(False)

        max_att = self.settings.get("max_login_attempts",
                                     MAX_LOGIN_ATTEMPTS)
        lock_sec = self.settings.get("lockout_seconds", LOCKOUT_SECONDS)

        if exc is None:
            self.key, self.data = key, data
        try:
            if exc is not None:
                raise exc
        except InvalidToken:
            # Drop the wrong key. Leaving it set kept `_reset_idle` armed
            # while the login screen was up, so the auto-lock timer fired
            # against a locked vault and stacked a second login frame on
            # top of the first.
            self.key = None
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
                    text=t("⚠️ Locked for {seconds}s",
                           seconds=penalty))
                self._login_attempts = 0  # reset window, keep streak
            else:
                self.error_label.configure(
                    text=t("⚠️ Wrong password ({remaining} attempts "
                           "left)", remaining=rem))
            # Persist before returning: the streak and the deadline have to
            # outlive this process to mean anything.
            self._persist_lockout_state()
            return
        except (OSError, ValueError) as read_error:
            # Unreadable or implausibly large vault file — not a bad
            # password, so don't count it as a failed attempt.
            log.error("Vault could not be read: %s", read_error,
                      exc_info=True)
            self.key = None
            self.error_label.configure(
                text=t("⚠️ Vault file could not be read"))
            return
        except Exception as unexpected:  # noqa: BLE001
            # The worker cannot let anything escape into a dead thread, so
            # a surprise arrives here rather than in Tk's handler.
            log.error("Unlock failed unexpectedly: %s", unexpected,
                      exc_info=True)
            self.key = None
            self.error_label.configure(
                text=t("⚠️ Vault file could not be read"))
            return

        self._login_attempts = 0
        self._failed_streak = 0  # success — reset escalation
        self._lockout_until = 0
        self._persist_lockout_state()
        log.info("Vault unlocked successfully%s.",
                 " (new vault created)" if is_new else "")
        if is_new:
            self._save_guarded()
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
            side=side_start(), padx=pad(16, 6))
        ctk.CTkLabel(top, text=t("Password Vault"),
                      font=ctk.CTkFont(family="Segoe UI", size=17,
                                        weight="bold"),
                      text_color=TEXT_PRI).pack(side=side_start())

        self.search_var = ctk.StringVar()

        self.search_var.trace_add("write",
                                   lambda *_: self._debounced_refresh())

        self._search_bar = make_search_bar(
            top, self.search_var,
            lambda: (self.data.get("categories", [])
                     if self.data else []),
            self._search_cat_filter,
            height=32, width=260)
        self._search_bar.pack(side=side_start(), padx=16)
        self._search_bar._entry.bind("<Escape>", self._clear_search)

        # Settings
        settings_btn = ctk.CTkButton(
            top, text="⚙", width=32, height=32,
            font=ctk.CTkFont(size=15), fg_color="transparent",
            hover_color=BG_TERT, corner_radius=8, text_color=TEXT_SEC,
            command=self.show_settings_menu)
        settings_btn.pack(side=side_end(), padx=pad(0, 10))
        tip(settings_btn,
            t("Settings — Preferences, export/import, security dashboard"))

        add_btn = ctk.CTkButton(
            top, text=t("＋  Add New"), width=110, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
            command=lambda: self.show_entry_dialog())
        add_btn.pack(side=side_end(), padx=pad(0, 6))
        tip(add_btn, t("Add a new password entry  (Ctrl+N)"))

        # Content

        content = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Sidebar

        self.sidebar = ctk.CTkFrame(content, width=200,
                                      fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.pack(side=side_start(), fill="y")
        self.sidebar.pack_propagate(False)


        ctk.CTkLabel(self.sidebar, text=t("Categories"),
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_SEC).pack(
            pady=(16, 8), padx=16, anchor=anchor_start())


        self.cat_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=SIDEBAR_BG)
        self.cat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))


        add_cat_btn = ctk.CTkButton(
            self.sidebar, text=t("＋  Category"), height=30,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", border_width=1,
            border_color=TEXT_QUAT, corner_radius=8,
            hover_color=BG_TERT, text_color=TEXT_SEC,
            command=self.show_add_cat_dialog)
        add_cat_btn.pack(pady=(0, 10), padx=12, fill="x")
        tip(add_cat_btn,
            t("Create a new category to organize passwords"))

        # Entries

        self.entries_panel = ctk.CTkScrollableFrame(
            content, fg_color=BG, corner_radius=0,
            scrollbar_button_color=BG_SEC)
        self.entries_panel.pack(side=side_end(), fill="both",
                                 expand=True)

        self.refresh_categories()
        self.refresh_entries()


    def _rebuild_ui(self):
        """Tear the main window down and build it again.

        Used when the language changes: every anchor, pack side and padding
        pair was resolved for the previous direction and Tk cannot revisit
        them. The vault itself is untouched — this is a redraw, not a lock.
        """
        self._destroy_open_dialogs()
        if self.mini_vault is not None:
            try:
                self.mini_vault.destroy()
            except tk.TclError:
                pass
            self.mini_vault = None
        if self.floating_widget is not None:
            try:
                self.floating_widget.destroy()
            except tk.TclError:
                pass
            self.floating_widget = None
        if self._main_frame is not None and self._main_frame.winfo_exists():
            self._main_frame.destroy()
            self._main_frame = None
        self._visible_limit = ENTRIES_PAGE_SIZE
        self.build_ui()

    def _search_cat_filter(self, cat):
        self.select_cat(cat)

    def _debounced_refresh(self):
        """Debounce search-triggered refreshes — 300ms idle then refresh."""
        if self._search_after_id:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.root.after(300, self._refresh_from_search)

    def _refresh_from_search(self):
        self._visible_limit = ENTRIES_PAGE_SIZE
        self.refresh_entries()

    # ─── Keyboard Shortcuts ──────────────────────────────────
    def _shortcut_actions(self) -> dict:
        return {
            "n": self.show_entry_dialog,
            "f": self._focus_search,
            "l": self._auto_lock,
            "e": self.show_export_dialog,
            "i": self.show_import_dialog,
        }

    def _bind_shortcuts(self):
        for letter, action in self._shortcut_actions().items():
            self.root.bind(f"<Control-{letter}>",
                            lambda _e, a=action: a())
        self._shortcuts_bound = True

    def _unbind_shortcuts(self):
        for letter in self._shortcut_actions():
            try:
                self.root.unbind(f"<Control-{letter}>")
            except tk.TclError:
                pass
        self._shortcuts_bound = False

    def _on_shortcut_keycode(self, event):
        """Run Ctrl shortcuts by physical key, whatever the input language.

        With a non-Latin layout active Tk reports the localized keysym, so
        the `<Control-n>` style bindings above never fire and the shortcuts
        silently stopped working.
        """
        if not self._shortcuts_bound or not (event.state & 0x4):
            return None
        letter = _SHORTCUT_KEYCODES.get(event.keycode)
        if letter is None or event.keysym.lower() == letter:
            return None  # Latin layout: the keysym binding already ran.
        action = self._shortcut_actions().get(letter)
        if action is None:
            return None
        action()
        return "break"

    def _focus_search(self):
        if self._search_bar:
            try:
                self._search_bar._entry.focus_set()
            except (tk.TclError, AttributeError):
                pass

    def _clear_search(self, _event=None):
        """Escape empties the query — the only way back to the full list
        was selecting the whole field and deleting it."""
        if self.search_var.get():
            self.search_var.set("")
        return "break"

    # ─── Settings Menu ───────────────────────────────────────
    def show_settings_menu(self):
        menu = tk.Menu(self.root, tearoff=0, **menu_style())
        menu.add_command(label=t("⚙️  Settings"),
                          command=self.show_settings_dialog)
        menu.add_command(label=t("🔑  Change Master Password"),
                          command=self.show_change_password_dialog)
        menu.add_separator()
        menu.add_command(label=t("🛡️  Security Dashboard"),
                          command=self.show_security_dashboard)
        menu.add_separator()
        menu.add_command(label=t("📤  Export Data  (Ctrl+E)"),
                          command=self.show_export_dialog)
        menu.add_command(label=t("📥  Import Data  (Ctrl+I)"),
                          command=self.show_import_dialog)
        menu.add_separator()
        menu.add_command(label=t("🛟  Encrypted Backup …"),
                          command=self.show_backup_export_dialog)
        menu.add_command(label=t("♻️  Restore From Backup …"),
                          command=self.show_backup_restore_dialog)
        menu.add_separator()
        trash_n = len(self.data.get("trash", []))
        menu.add_command(
            label=t("🗑️  Recycle Bin ({count})", count=trash_n),
            command=self.show_trash_dialog)
        menu.add_separator()
        menu.add_command(label=t("🔒  Lock Vault  (Ctrl+L)"),
                          command=self._auto_lock)
        menu.add_separator()
        menu.add_command(label=t("ℹ️  About"),
                          command=self.show_about_dialog)
        menu.add_separator()
        menu.add_command(label=t("✕  Exit"), command=self.confirm_quit)
        try:
            menu.post(self.root.winfo_pointerx(),
                      self.root.winfo_pointery())
        except tk.TclError:
            pass

    # ─── About Dialog ────────────────────────────────────────
    def show_about_dialog(self):
        from password_vault.ui.dialogs import about
        about.show(self)

    # ─── Settings Dialog ─────────────────────────────────────
    def show_settings_dialog(self):
        dlg = self._make_dialog("Settings", 480, 620)

        dialog_header(dlg, "Settings", icon="⚙️", size=17,
                      pady=(14, 6))

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
                row, text=f"{icon}  {t(label)}",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_PRI, anchor=anchor_start())
            lbl_w.pack(side=side_start(), fill="x", expand=True)
            return row, lbl_w

        # ── SECURITY ──
        g_sec = ios_group(scroll, "Security")

        r, lbl = setting_row(g_sec, "🔒", "Auto-Lock", idx=0)
        al_map = {t("{n} min", n=n): n for n in (1, 2, 5, 10, 15, 30)}
        al_map[t("Never")] = 0
        al_rev = {v: k for k, v in al_map.items()}
        al_var = ctk.StringVar(
            value=al_rev.get(s["auto_lock_minutes"], t("{n} min", n=5)))
        al_opt = ctk.CTkOptionMenu(
            r, values=list(al_map.keys()), variable=al_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        al_opt.pack(side=side_end())
        tip(lbl, t("Lock the vault after this period of inactivity. "
                 "'Never' disables auto-lock."))

        r2, lbl2 = setting_row(g_sec, "🛡️", "Max Login Attempts", idx=1)
        att_map = {"3": 3, "5": 5, "10": 10, "15": 15}
        att_var = ctk.StringVar(value=str(s["max_login_attempts"]))
        att_opt = ctk.CTkOptionMenu(
            r2, values=list(att_map.keys()), variable=att_var,
            width=80, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        att_opt.pack(side=side_end())
        tip(lbl2, t("Maximum wrong password attempts before lockout."))

        r3, lbl3 = setting_row(g_sec, "⏱️", "Lockout Duration", idx=2)
        lo_map = {t("{n} sec", n=n): n for n in (15, 30, 60)}
        lo_map[t("{n} min", n=2)] = 120
        lo_map[t("{n} min", n=5)] = 300
        lo_rev = {v: k for k, v in lo_map.items()}
        lo_var = ctk.StringVar(
            value=lo_rev.get(s["lockout_seconds"], t("{n} sec", n=30)))
        lo_opt = ctk.CTkOptionMenu(
            r3, values=list(lo_map.keys()), variable=lo_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        lo_opt.pack(side=side_end())
        tip(lbl3, t("How long the vault stays locked after "
                  "too many failed attempts."))

        r4, lbl4 = setting_row(g_sec, "📋", "Clear Clipboard", idx=3)
        cl_map = {t("Off"): 0}
        cl_map.update({t("{n} sec", n=n): n for n in (10, 15, 30, 60)})
        cl_rev = {v: k for k, v in cl_map.items()}
        cl_var = ctk.StringVar(
            value=cl_rev.get(s["clipboard_clear_seconds"], t("Off")))
        cl_opt = ctk.CTkOptionMenu(
            r4, values=list(cl_map.keys()), variable=cl_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        cl_opt.pack(side=side_end())
        tip(lbl4, t("Automatically clear copied passwords "
                  "from clipboard after this time."))

        # ── PASSWORD GENERATOR ──
        g_gen = ios_group(scroll, "Password Generator Defaults")

        r5, lbl5 = setting_row(g_gen, "📏", "Default Length", idx=0)
        gl_var = ctk.IntVar(value=s.get("gen_length", 16))
        gl_lbl = ctk.CTkLabel(r5, text=str(gl_var.get()),
                                font=ctk.CTkFont(size=11, weight="bold"),
                                text_color=TEXT_PRI, width=28)
        gl_lbl.pack(side=side_end())

        def on_gl(v):
            gl_var.set(int(float(v)))
            gl_lbl.configure(text=str(int(float(v))))

        gl_slider = ctk.CTkSlider(
            r5, from_=6, to=40, number_of_steps=34, command=on_gl,
            width=140, fg_color=BG_TERT, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER)
        gl_slider.set(gl_var.get())
        gl_slider.pack(side="right", padx=(0, 8))
        tip(lbl5, t("Default password length when opening the generator."))

        r6, lbl6 = setting_row(g_gen, "🔤", "Uppercase (ABC)", idx=1)
        gen_upper = ctk.CTkSwitch(r6, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_upper.pack(side=side_end())
        if s.get("gen_upper", True):
            gen_upper.select()
        tip(lbl6, t("Include uppercase letters (A-Z)."))

        r7, lbl7 = setting_row(g_gen, "🔡", "Lowercase (abc)", idx=2)
        gen_lower = ctk.CTkSwitch(r7, text="", width=46,
                                    fg_color=BG_TERT, progress_color=GREEN,
                                    button_color=TEXT_PRI)
        gen_lower.pack(side=side_end())
        if s.get("gen_lower", True):
            gen_lower.select()
        tip(lbl7, t("Include lowercase letters (a-z)."))

        r8, lbl8 = setting_row(g_gen, "🔢", "Digits (0-9)", idx=3)
        gen_digits = ctk.CTkSwitch(r8, text="", width=46,
                                     fg_color=BG_TERT, progress_color=GREEN,
                                     button_color=TEXT_PRI)
        gen_digits.pack(side=side_end())
        if s.get("gen_digits", True):
            gen_digits.select()
        tip(lbl8, t("Include digits (0-9)."))

        r9, lbl9 = setting_row(g_gen, "🔣", "Symbols (#$%&)", idx=4)
        gen_symbols = ctk.CTkSwitch(r9, text="", width=46,
                                      fg_color=BG_TERT, progress_color=GREEN,
                                      button_color=TEXT_PRI)
        gen_symbols.pack(side=side_end())
        if s.get("gen_symbols", True):
            gen_symbols.select()
        tip(lbl9, t("Include special symbols (!@#$%&)."))

        # ── APPEARANCE ──
        g_app = ios_group(scroll, "Appearance")

        r_th, lbl_th = setting_row(g_app, "🌗", "Theme", idx=0)
        theme_labels = {t("System"): "System", t("Dark"): "Dark",
                        t("Light"): "Light"}
        assert set(theme_labels.values()) == set(THEME_MODES)
        theme_names = {mode: label
                       for label, mode in theme_labels.items()}
        th_var = ctk.StringVar(
            value=theme_names.get(s.get("theme", "Dark"), t("Dark")))
        th_opt = ctk.CTkOptionMenu(
            r_th, values=list(theme_labels), variable=th_var,
            width=100, height=28, font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI,
            command=lambda choice: ctk.set_appearance_mode(
                theme_labels.get(choice, "Dark")))
        th_opt.pack(side=side_end())
        tip(lbl_th, t("Light, dark, or follow the Windows setting. "
                    "Applies immediately."))

        r_lang, lbl_lang = setting_row(g_app, "🌐", t("Language"), idx=1)
        lang_var = ctk.StringVar(
            value=label_for(s.get("language", "English")))
        lang_opt = ctk.CTkOptionMenu(
            r_lang, values=[label_for(v) for v in LANGUAGE_VALUES],
            variable=lang_var, width=100, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=BG_TERT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
            dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
        lang_opt.pack(side=side_end())
        tip(lbl_lang, t("The window is rebuilt when the language changes."))

        r10, lbl10 = setting_row(g_app, "🎨", t("Default Card Color"), idx=2)
        tip(lbl10, t("Default color for new password entries."))

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
                text_color=TEXT_ON_ACCENT,
                command=lambda k=ckey: _sel_def_color(k))
            b.pack(side="left", padx=3)
            color_btns[ckey] = b
            tip(b, t("{label} — set as default card color",
                     label=t(info["label"])))

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
        start_min.pack(side=side_end())
        if s.get("start_minimized", False):
            start_min.select()
        tip(lbl11, t("Start the app minimized to the floating widget."))

        # ── SAVE ──
        saved_theme = {"kept": False}

        def _revert_theme_preview(event):
            # The toplevel is in every child's bindtags, so <Destroy> also
            # arrives here for each child widget.
            if event.widget is not dlg or saved_theme["kept"]:
                return
            # The picker previews immediately; dismissing without saving must
            # not leave the app in a mode that is not stored.
            ctk.set_appearance_mode(self.settings.get("theme", "Dark"))

        dlg.bind("<Destroy>", _revert_theme_preview, add="+")

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
            self.settings["theme"] = theme_labels.get(
                th_var.get(), "Dark")
            new_language = value_for(lang_var.get())
            language_changed = (
                new_language != self.settings.get("language", "English"))
            self.settings["language"] = new_language
            saved_theme["kept"] = True
            save_settings(self.settings)
            self._reset_idle(force=True)
            dlg.destroy()
            if language_changed:
                # Tk fixes anchor, justify, pack side and padding when a
                # widget is created and offers no way to re-flow them, so
                # the direction can only change by building again.
                set_language(new_language)
                self._rebuild_ui()

        bottom = ctk.CTkFrame(dlg, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 12))
        save_btn = ctk.CTkButton(
            bottom, text=t("💾  Save Settings"), height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=apply_settings)
        save_btn.pack(fill="x")
        tip(save_btn, t("Save all settings and close"))

    # ─── Change Master Password ──────────────────────────────
    def show_change_password_dialog(self):
        from password_vault.ui.dialogs import change_password
        change_password.show(self)

    # ─── Categories ──────────────────────────────────────────
    def refresh_categories(self):
        for w in self.cat_frame.winfo_children():
            w.destroy()
        entries = self.data["entries"]
        # One pass over entries instead of one pass per category.
        per_cat: dict[str, int] = {}
        for e in entries:
            key = e.get("category")
            if key:
                per_cat[key] = per_cat.get(key, 0) + 1
        cats = ["All"] + self.data.get("categories", [])
        for cat in cats:
            count = len(entries) if cat == "All" else per_cat.get(cat, 0)
            emoji = "🗂️" if cat == "All" else cat_emoji(cat)
            shown = t("All") if cat == "All" else cat
            active = cat == self.current_category


            row = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            btn = ctk.CTkButton(

                row, text=f" {emoji}  {shown}   ({count})",
                font=ui_font(12, "bold" if active else "normal"),
                fg_color=SIDEBAR_SEL if active else "transparent",
                hover_color=(ACCENT_HOVER if active else BG_TERT),
                text_color=TEXT_ON_ACCENT if active else TEXT_PRI,
                anchor=anchor_start(), height=34, corner_radius=8,
                command=lambda c=cat: self.select_cat(c))
            btn.pack(side=side_start(), fill="x", expand=True)
            tip(btn,
                t("Show all entries") if cat == "All"
                else t("Show entries in {category}", category=cat))

            if cat != "All":
                del_btn = ctk.CTkButton(
                    row, text="✕", width=26, height=26,
                    font=ui_font(10, family=None), fg_color="transparent",
                    hover_color=RED_HOVER, corner_radius=6,
                    text_color=TEXT_TERT,
                    command=lambda c=cat: self.confirm_delete_category(c))
                del_btn.pack(side=side_end(), padx=pad(2, 0))
                tip(del_btn, t("Delete '{category}' category",
                               category=cat))

    def select_cat(self, cat):
        self.current_category = cat
        self._visible_limit = ENTRIES_PAGE_SIZE
        self.refresh_categories()
        self.refresh_entries()


    # ─── Delete Category ─────────────────────────────────────
    def confirm_delete_category(self, cat_name):
        n = sum(1 for e in self.data["entries"]
                if e.get("category") == cat_name)
        msg = t('Delete "{name}"?', name=cat_name)
        if n > 0:
            msg += "\n" + t('{count} entries → "General".', count=n)

        def do_del(dlg):
            for e in self.data["entries"]:
                if e.get("category") == cat_name:
                    e["category"] = "General"
            self.data["categories"].remove(cat_name)
            if "General" not in self.data["categories"]:
                self.data["categories"].insert(0, "General")
            self._save_guarded()
            dlg.destroy()
            if self.current_category == cat_name:
                self.current_category = "All"
            self.refresh_categories()
            self.refresh_entries()

        self._confirm("Delete Category?", msg, icon="⚠️",
                      confirm_text="Delete", on_confirm=do_del,
                      window_title="Delete Category", size=(380, 190))

    # ─── Entries ─────────────────────────────────────────────
    def refresh_entries(self):
        for w in self.entries_panel.winfo_children():
            w.destroy()

        search = ""
        if hasattr(self, "search_var"):
            search = self.search_var.get()
        entries = filter_entries(
            self.data["entries"], self.current_category, search)
        entries = sort_entries_pinned_first(entries)
        if not entries:

            ef = ctk.CTkFrame(self.entries_panel, fg_color="transparent")
            ef.pack(expand=True, fill="both")
            ctk.CTkLabel(ef, text="📭",
                          font=ctk.CTkFont(size=48)).pack(pady=(80, 8))
            ctk.CTkLabel(ef, text=t("No passwords yet"),
                          font=ctk.CTkFont(family="Segoe UI", size=15),
                          text_color=TEXT_TERT).pack()
            ctk.CTkLabel(ef,
                          text=t("Click '＋ Add New' to get started"),
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          text_color=TEXT_QUAT).pack(pady=(4, 0))
            return
        for entry in entries[:self._visible_limit]:
            self._card(entry)
        hidden = len(entries) - self._visible_limit
        if hidden > 0:
            self._add_show_more(hidden)

    def _add_show_more(self, hidden: int):
        """Footer that extends the render window by one more page."""
        btn = ctk.CTkButton(
            self.entries_panel,
            text=t("⬇  Show more  ({hidden} hidden)", hidden=hidden),
            height=34, font=ui_font(12),
            fg_color=BG_SEC, hover_color=BG_TERT, corner_radius=8,
            text_color=TEXT_SEC, command=self._show_more_entries)
        btn.pack(fill="x", padx=8, pady=(6, 10))
        tip(btn, t("Render the next {count} entries",
                   count=ENTRIES_PAGE_SIZE))

    def _show_more_entries(self):
        self._visible_limit += ENTRIES_PAGE_SIZE
        self.refresh_entries()

    def _card(self, entry):

        color_key = entry.get("color", "default")
        cc = CARD_COLORS.get(color_key, CARD_COLORS["default"])

        card = ctk.CTkFrame(self.entries_panel, fg_color=cc["bg"],
                              corner_radius=10)
        card.pack(fill="x", pady=2, padx=8)

        def _on_right_click(event, e=entry):
            self._show_context_menu(event, e)

        has_strip = add_color_strip(card, cc)

        inner = ctk.CTkFrame(card, fg_color="transparent")

        inner.pack(fill="x", padx=(14 if has_strip else 12), pady=6)


        # Row 1: Pin + Title + Category badge + Age + Edit + Delete
        r1 = ctk.CTkFrame(inner, fg_color="transparent")

        r1.pack(fill="x", pady=(0, 2))

        # Pin toggle
        is_pinned = entry.get("pinned", False)
        pin_btn = ctk.CTkButton(
            r1, text="📌" if is_pinned else "○",
            width=24, height=24, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5,
            font=ui_font(11 if is_pinned else 9, family=None),
            text_color=YELLOW if is_pinned else TEXT_QUAT,
            command=lambda: self._toggle_pin(entry))
        pin_btn.pack(side=side_start(), padx=pad(0, 2))
        tip(pin_btn,
            t("Unpin from top") if is_pinned else t("Pin to top"))

        emoji = cat_emoji(entry.get("category", ""))

        full_title = entry.get("title", "")
        title_lbl = ctk.CTkLabel(
            r1, text=f"{emoji}  {elide(full_title, TITLE_MAX_CHARS)}",
            font=ui_font(13, "bold"), text_color=TEXT_PRI)
        title_lbl.pack(side=side_start())
        if len(full_title) > TITLE_MAX_CHARS:
            tip(title_lbl, full_title)
        ctk.CTkLabel(r1, text=f" {entry.get('category', '')} ",
                      font=ui_font(9),
                      text_color=TEXT_SEC, fg_color=BADGE_BG,
                      corner_radius=4).pack(side=side_start(),
                                            padx=pad(8, 0))

        # Delete
        del_btn = ctk.CTkButton(
            r1, text="🗑", width=24, height=24, fg_color="transparent",
            hover_color=RED_HOVER, corner_radius=5,
            font=ui_font(11, family=None),
            command=lambda: self.confirm_delete(entry))
        del_btn.pack(side=side_end(), padx=1)
        tip(del_btn, t("Move to Recycle Bin"))

        # Edit
        edit_btn = ctk.CTkButton(
            r1, text="✏", width=24, height=24, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5,
            font=ui_font(11, family=None),
            command=lambda: self.show_entry_dialog(entry))
        edit_btn.pack(side=side_end(), padx=1)
        tip(edit_btn, t("Edit this entry"))

        # Age
        age_t, age_c = password_age_text(
            entry.get("modified_at") or entry.get("created_at"))
        if age_t:
            ctk.CTkLabel(r1, text=age_t, font=ui_font(9, family=None),
                          text_color=age_c).pack(
                side=side_end(), padx=pad(0, 6))

        # Row 2: User + Copy user + URL + Password + Eye + Copy pass
        r2 = ctk.CTkFrame(inner, fg_color="transparent")

        r2.pack(fill="x", pady=(0, 1))

        ctk.CTkLabel(r2, text=f"👤 {entry.get('username', '')}",
                      font=ui_font(11),
                      text_color=TEXT_SEC,
                      anchor=anchor_start()).pack(side=side_start())
        cu = ctk.CTkButton(
            r2, text="📋", width=28, height=22,
            font=ui_font(10, family=None),
            fg_color=GREEN, hover_color=GREEN_HOVER,
            text_color=TEXT_ON_GREEN, corner_radius=5,
            command=lambda: self._copy_to_clipboard(
                entry.get("username", ""), cu))

        cu.pack(side=side_start(), padx=pad(6, 0))
        tip(cu, t("Copy username"))

        # URL button
        url = entry.get("url", "")
        if url:
            url_btn = ctk.CTkButton(
                r2, text="🌐", width=28, height=22,
                font=ui_font(10, family=None),
                fg_color=BG_TERT, hover_color=TEXT_QUAT,
                text_color=TEAL, corner_radius=5,
                command=lambda u=url: self._open_url(u))
            url_btn.pack(side=side_start(), padx=pad(4, 0))
            tip(url_btn, t("Open {url}", url=url))

        pwd = entry.get("password", "")

        cp = ctk.CTkButton(
            r2, text=t("🔑 Copy"), width=65, height=22,
            font=ui_font(10, family=None),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT_ON_ACCENT, corner_radius=5,
            command=lambda: self._copy_to_clipboard(pwd, cp))
        cp.pack(side=side_end())

        tip(cp, t("Copy password"))

        # Fixed-width mask: one dot per character published the exact length
        # of every password to anyone glancing at the screen.
        plbl = ctk.CTkLabel(r2, text=PASSWORD_MASK,
                              font=ui_font(11, family=None),
                              text_color=TEXT_TERT, anchor=anchor_end(),
                              wraplength=240, justify=justify_end())
        plbl.pack(side=side_end(), padx=pad(0, 4))

        revealed = {"on": False}

        def toggle(lbl=plbl, real=pwd):
            revealed["on"] = not revealed["on"]
            # Show the whole value: the old 20-character cut made the user
            # read a password that was not the one stored.
            lbl.configure(text=real if revealed["on"] else PASSWORD_MASK)
            eye.configure(text="🙈" if revealed["on"] else "👁")

        eye = ctk.CTkButton(
            r2, text="👁", width=24, height=22, fg_color="transparent",
            hover_color=BG_TERT, corner_radius=5,
            font=ui_font(10, family=None), command=toggle)
        eye.pack(side=side_end(), padx=pad(0, 2))
        tip(eye, t("Show / hide password"))

        # Row 3: URL text (subtle, if exists)
        if url:
            ctk.CTkLabel(inner,
                          text=f"🔗 {url[:60]}{'…' if len(url) > 60 else ''}",
                          font=ui_font(10),
                          text_color=TEAL, anchor=anchor_start(),
                          cursor="hand2").pack(
                fill="x", pady=(1, 0))

        # Row 4: Notes
        notes = entry.get("notes", "")
        if notes:

            ctk.CTkLabel(inner, text=notes,
                          font=ui_font(10),
                          text_color=TEXT_TERT, anchor=anchor_start(),
                          wraplength=400,
                          justify=justify_start()).pack(
                fill="x", pady=(2, 0))

        # Bind right-click to the entire card and every child so the menu
        # opens regardless of where on the card the user clicks.
        bind_right_click_recursive(card, _on_right_click)

    def _toggle_pin(self, entry):
        entry["pinned"] = not entry.get("pinned", False)
        self._schedule_save()
        self.refresh_entries()

    def _save_and_refresh(self):
        """Save data and refresh all views (entries + categories + mini vault)."""
        self._save_guarded()
        self.refresh_categories()
        self.refresh_entries()
        if (self.mini_vault
                and self.mini_vault.winfo_exists()):
            try:
                self.mini_vault._refresh()
            except tk.TclError:
                pass

    def _clear_clipboard(self):
        """Clear the clipboard, but only if it still holds our value.

        The old unconditional wipe destroyed whatever the user had copied
        from another app while the timer was pending.
        """
        self._clipboard_timer = None
        expected = self._clipboard_digest
        self._clipboard_digest = None
        if expected is None:
            return
        try:
            current = pyperclip.paste()
        except (OSError, RuntimeError, pyperclip.PyperclipException) as exc:
            log.warning("Could not read the clipboard: %s", exc)
            return
        if not current or password_hash(current) != expected:
            return
        try:
            pyperclip.copy("")
        except (OSError, RuntimeError, pyperclip.PyperclipException) as exc:
            log.warning("Could not clear the clipboard: %s", exc)

    # ─── Right-Click Context Menu ─────────────────────────────
    def _show_context_menu(self, event, entry, parent=None):
        """Show a right-click context menu for a password entry card."""
        self._reset_idle()
        owner = parent or self.root
        menu = tk.Menu(owner, tearoff=0, relief="flat", bd=1,
                       selectcolor=resolve(ACCENT), **menu_style())

        username = entry.get("username", "")
        password = entry.get("password", "")
        url = entry.get("url", "")

        # ── Copy actions ──
        menu.add_command(
            label=t("📋  Copy Username"),
            command=lambda: self._copy_to_clipboard(username))
        menu.add_command(
            label=t("🔑  Copy Password"),
            command=lambda: self._copy_to_clipboard(password))

        menu.add_separator()

        # ── URL / Browser ──
        if url:
            menu.add_command(
                label=t("🌐  Open URL in Browser"),
                command=lambda: self._open_url(url))
            menu.add_command(
                label=t("🌐  Open URL + Copy Username"),
                command=lambda: self._open_url_with_creds(
                    url, username, password))
        else:
            menu.add_command(
                label=t("🌐  Open URL in Browser"),
                state="disabled")

        # ── SSH / RDP Session ── only for entries that really look like a
        # remote host, not for every entry that happens to have a URL.
        if self._looks_remote(entry, url):
            menu.add_separator()
            menu.add_command(
                label=t("🖥️  SSH Session …"),
                command=lambda: self._show_ssh_dialog(entry))
            menu.add_command(
                label=t("🖥️  RDP Session …"),
                command=lambda: self._show_rdp_dialog(entry))

        menu.add_separator()

        # ── Edit / Delete ──
        menu.add_command(
            label=t("✏️  Edit Entry"),
            command=lambda: self.show_entry_dialog(entry))
        menu.add_command(
            label=t("📌  Pin / Unpin"),
            command=lambda: self._toggle_pin(entry))
        menu.add_command(
            label=t("🗑️  Delete"),
            command=lambda: self.confirm_delete(entry))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    @staticmethod
    def _looks_remote(entry: dict, url: str) -> bool:
        """True when the entry plausibly describes a machine to log into.

        Any ordinary web URL yields a hostname, so a hostname alone used to
        put SSH and RDP actions on webmail entries. A remote host is an
        explicit ssh/rdp scheme, a bare host or IP with no web scheme, or a
        server-like category.
        """
        if entry.get("category", "").strip().lower() in REMOTE_CATEGORIES:
            return True
        raw = (url or "").strip()
        if not raw:
            return False
        scheme = raw.split("://", 1)[0].lower() if "://" in raw else ""
        if scheme:
            return scheme in ("ssh", "sftp", "rdp", "telnet", "vnc")
        # No scheme: a bare "10.0.0.5" or "db01.internal" is a host, while
        # "example.com/login" is a web address someone typed short.
        return "/" not in raw and "?" not in raw

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
        self._open_url(url)

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

    # ─── SSH / RDP Connection Dialog ───────────────────────
    def _show_ssh_dialog(self, entry):
        self._show_remote_session_dialog(entry, kind="ssh")

    def _show_rdp_dialog(self, entry):
        self._show_remote_session_dialog(entry, kind="rdp")

    def _show_remote_session_dialog(self, entry, *, kind: str):
        """Unified dialog for SSH / RDP session setup."""
        is_ssh = kind == "ssh"
        title = t("SSH Session") if is_ssh else t("RDP Session")
        header = (t("🖥️  SSH Session") if is_ssh
                  else t("🖥️  Remote Desktop (RDP)"))
        default_port = 22 if is_ssh else 3389
        height = 480 if is_ssh else 400
        btn_color = GREEN if is_ssh else ACCENT
        btn_hover = GREEN_HOVER if is_ssh else ACCENT_HOVER
        btn_text_color = TEXT_ON_GREEN if is_ssh else TEXT_ON_ACCENT

        dlg = self._make_dialog(title, 420, height)

        dialog_header(dlg, header, size=15, pady=(12, 2))
        ctk.CTkLabel(
            dlg, text=t("Entry: {title}", title=entry.get("title", "")),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_SEC).pack(pady=(0, 8))

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 6))

        # Host / IP
        pre_host = self._extract_host(entry.get("url", ""), entry)
        ctk.CTkLabel(form, text=t("Host / IP"),
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", pady=(4, 1))
        host_e = ctk.CTkEntry(
            form, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI,
            placeholder_text=t("e.g. 192.168.1.10 or server.example.com"))
        host_e.pack(fill="x", pady=(0, 6))
        if pre_host:
            host_e.insert(0, pre_host)

        # Username (SSH only)
        user_e = None
        if is_ssh:
            ctk.CTkLabel(form, text=t("Username"),
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          text_color=TEXT_PRI, anchor="w").pack(
                fill="x", pady=(2, 1))
            user_e = ctk.CTkEntry(
                form, height=34, font=ctk.CTkFont(size=12),
                fg_color=INPUT_BG, border_width=0, corner_radius=8,
                text_color=TEXT_PRI, placeholder_text=t("username"))
            user_e.pack(fill="x", pady=(0, 6))
            user_e.insert(0, entry.get("username", ""))

        # Port
        port_row = ctk.CTkFrame(form, fg_color="transparent")
        port_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(port_row, text=t("Port"),
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_PRI, anchor="w").pack(side="left")
        port_e = ctk.CTkEntry(
            port_row, width=80, height=34, font=ctk.CTkFont(size=12),
            fg_color=INPUT_BG, border_width=0, corner_radius=8,
            text_color=TEXT_PRI)
        port_e.pack(side="left", padx=(10, 0))
        port_e.insert(0, str(self._extract_port(
            entry.get("url", ""), default_port)))

        # SSH Client selector (SSH only)
        clients = self._detect_ssh_clients() if is_ssh else []
        client_var = None
        if is_ssh:
            client_names = ([c[0] for c in clients] if clients
                            else [t("No SSH client found")])
            ctk.CTkLabel(form, text=t("SSH Client"),
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

        ctk.CTkLabel(
            form, text=t("💡 Password will be copied to clipboard"),
            font=ctk.CTkFont(size=9), text_color=TEXT_TERT).pack(fill="x")

        def connect():
            host = host_e.get().strip()
            port_str = port_e.get().strip()
            if not host:
                err.configure(text=t("⚠️ Host / IP is required"))
                return
            try:
                port = int(port_str)
            except ValueError:
                err.configure(text=t("⚠️ Invalid port number"))
                return

            if is_ssh:
                user = user_e.get().strip() if user_e else ""
                if not clients:
                    err.configure(text=t("⚠️ No SSH client found on system"))
                    return
                selected = client_var.get() if client_var else ""
                client_path = next(
                    (path for name, path in clients if name == selected),
                    "")
                if not client_path:
                    err.configure(text=t("⚠️ SSH client not found"))
                    return
                self._copy_to_clipboard(entry.get("password", ""),
                                         force_clear_seconds=10)
                dlg.destroy()
                self._launch_ssh(client_path, selected, host, user,
                                 port, entry.get("title", ""))
            else:
                self._copy_to_clipboard(entry.get("password", ""),
                                         force_clear_seconds=10)
                dlg.destroy()
                host = self._sanitize_shell_arg(host)
                try:
                    rdp_target = (f"{host}:{port}"
                                  if port != default_port else host)
                    subprocess.Popen(["mstsc", f"/v:{rdp_target}"])
                except OSError as exc:
                    log.warning("Failed to launch RDP: %s", exc)

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkButton(
            btn_row, text=t("Cancel"), width=90, height=36,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
            command=dlg.destroy).pack(side="left")
        connect_btn = ctk.CTkButton(
            btn_row, text=t("🖥️  Connect"), height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=btn_color, hover_color=btn_hover,
            text_color=btn_text_color, corner_radius=8, command=connect)
        connect_btn.pack(side="right", fill="x", expand=True, padx=(8, 0))
        tip(connect_btn,
            t("Start {kind} session (password copied to clipboard)",
              kind=kind.upper()))
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
        cleaned = re.sub(r'[^a-zA-Z0-9.\-_@:/\\ ]', '', value)
        # A leading hyphen survives that filter and every client here reads
        # its arguments as options first, so a host imported from an
        # untrusted file could arrive as a flag rather than a destination.
        return cleaned.lstrip("-")

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

    # ─── Password Generator Dialog ───────────────────────────
    def _show_generator(self, target_entry):
        from password_vault.ui.dialogs import generator
        generator.show(self, target_entry)

    # ─── Add / Edit Entry Dialog ─────────────────────────────
    def show_entry_dialog(self, entry=None):
        is_edit = entry is not None
        dlg = self._make_dialog(
            "Edit Password" if is_edit else "New Password", 420, 540)

        dialog_header(
            dlg, "Edit Password" if is_edit else "New Password",
            icon="✏️" if is_edit else "＋", size=14,
            pady=(8, 4))

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
        ctk.CTkLabel(pw_row, text=t("Password"),
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
            text_color=TEXT_ON_GREEN,
            command=lambda: self._show_generator(pass_e))
        gen_btn.pack(side="right")
        tip(gen_btn, t("Open password generator"))

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
        tip(eye_btn, t("Show / hide password"))

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
        tip(str_bar, t("Password strength indicator"))

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
                _pw_hash_map[password_hash(op)] = oe.get("title", "?")

        def _check_dup():
            """Duplicate check (runs after debounce delay)."""
            pw = pass_e.get()
            if pw:
                dupe_title = _pw_hash_map.get(password_hash(pw))
                if dupe_title:
                    dup_lbl.configure(
                        text=t("⚠️ Same password used in '{title}'",
                               title=dupe_title))
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
                text_color=TEXT_ON_ACCENT,
                command=lambda k=ckey: _select_color(k))
            b.pack(side="left", padx=2)
            color_btns[ckey] = b
            tip(b, t("{label} card color", label=t(info["label"])))

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
                err.configure(text=t("⚠️ Title is required"))
                return
            if not p:
                err.configure(text=t("⚠️ Password is required"))
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
            self._save_guarded()
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()


        save_btn = ctk.CTkButton(
            bottom,
            text=(t("💾  Save Changes") if is_edit
                  else t("💾  Save")),
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=save)
        save_btn.pack(fill="x")
        tip(save_btn, t("Save this password entry"))
        dlg.bind("<Control-Return>", lambda _e: save())
        # Enter submits from any single-line field, the way the smaller
        # dialogs already behave. The Notes box keeps Enter for newlines.
        for field in (title_e, url_e, user_e, pass_e):
            field.bind("<Return>", lambda _e: save())
        # A CTkTextbox swallows Tab as an indent character, which trapped
        # keyboard focus in Notes with no way out.
        def _leave_notes(target):
            def handler(_event):
                target.focus_set()
                return "break"
            return handler

        notes_tb.bind("<Tab>", _leave_notes(save_btn))
        notes_tb.bind("<Shift-Tab>", _leave_notes(pass_e))
        title_e.focus()

    # ─── Delete Confirm (→ Recycle Bin) ──────────────────────
    def confirm_delete(self, entry):

        def do_del(dlg):

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
            self._save_guarded()
            dlg.destroy()
            self.refresh_categories()
            self.refresh_entries()

        self._confirm(
            "Move to Recycle Bin?",
            t('Delete "{title}"?\nYou can restore it from the '
              "Recycle Bin.", title=entry.get("title", "")),
            icon="⚠️", confirm_text="Delete", on_confirm=do_del,
            window_title="Delete", size=(360, 190))

    # ─── Add Category ────────────────────────────────────────
    def show_add_cat_dialog(self):

        dlg = self._make_dialog("New Category", 350, 185)

        dialog_header(dlg, "New Category", icon="📁", size=15,
                      pady=(14, 10))
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
                err.configure(text=t("⚠️ Enter a name"))
                return
            if name in self.data["categories"]:
                err.configure(text=t("⚠️ Already exists"))
                return
            self.data["categories"].append(name)
            self._save_guarded()
            dlg.destroy()
            self.refresh_categories()

        cat_e.bind("<Return>", lambda e: save())

        ctk.CTkButton(
            frm, text=t("＋  Add"), height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=save).pack(fill="x")

    # ─── Export / Import Dialogs ─────────────────────────────
    def show_export_dialog(self):
        from password_vault.ui.dialogs import data_io
        data_io.show_export(self)

    def show_import_dialog(self):
        from password_vault.ui.dialogs import data_io
        data_io.show_import(self)

    # ─── Recycle Bin Dialog ──────────────────────────────────
    def show_trash_dialog(self):
        from password_vault.ui.dialogs import trash
        trash.show(self)

    # ─── Encrypted Backup Dialogs ────────────────────────────
    def show_backup_export_dialog(self):
        from password_vault.ui.dialogs import backup
        backup.show_export(self)

    def show_backup_restore_dialog(self):
        from password_vault.ui.dialogs import backup
        backup.show_restore(self)

    # ─── Security Dashboard ──────────────────────────────────
    def show_security_dashboard(self):
        from password_vault.ui.dialogs import security_dashboard
        security_dashboard.show(self)

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
        self._flush_pending_save()
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

    def confirm_quit(self):
        """Ask before exiting; the X button only minimizes, so quitting was
        previously a single unconfirmed click in the widget menu."""
        self._confirm(
            "Exit Password Vault?",
            "The vault will be locked and closed.",
            icon="🚪", confirm_text="Exit",
            on_confirm=lambda _dlg: self.quit_app(),
            window_title="Exit Password Vault", big_icon=True)

    def quit_app(self):

        log.info("Application exiting.")
        self._flush_pending_save(notify=False)
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
        """Center *dlg* on the parent, kept fully inside the screen."""
        dlg.update_idletasks()

        cx = (self.root.winfo_x()
              + (self.root.winfo_width() // 2) - (w // 2))
        cy = (self.root.winfo_y()
              + (self.root.winfo_height() // 2) - (h // 2))
        # Clamp to the visible desktop: a parent near an edge, or moved to a
        # smaller secondary monitor, used to push dialogs partly offscreen.
        screen_w = dlg.winfo_screenwidth()
        screen_h = dlg.winfo_screenheight()
        cx = max(0, min(cx, screen_w - w))
        cy = max(0, min(cy, screen_h - h))
        dlg.geometry(f"{w}x{h}+{cx}+{cy}")

    def _make_dialog(self, title: str, w: int, h: int) -> ctk.CTkToplevel:
        """Create a standard centered modal dialog."""
        self._reset_idle()
        parent = self._grab_stack[-1] if self._grab_stack else self.root
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t(title))
        dlg.geometry(f"{w}x{h}")
        # Resizable with a floor instead of a fixed size: at Windows display
        # scaling above 100% the fixed geometry clipped the content.
        dlg.minsize(w, h)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self._grab_stack.append(dlg)
        self._center(dlg, w, h)

        def _release_grab(event, dlg=dlg, parent=parent):
            # The toplevel sits in every child's bindtags, so <Destroy> also
            # arrives here for each child widget.
            if event.widget is not dlg:
                return
            if dlg in self._grab_stack:
                self._grab_stack.remove(dlg)
            # Hand the grab back, otherwise closing a nested dialog left the
            # dialog underneath it non-modal.
            top = self._grab_stack[-1] if self._grab_stack else None
            try:
                if top is not None and top.winfo_exists():
                    top.grab_set()
                elif parent is self.root:
                    self.root.grab_release()
            except tk.TclError:
                pass

        dlg.bind("<Destroy>", _release_grab, add="+")
        # Esc closes the dialog. Individual dialogs may bind <Return> to
        # their primary action (Save/Connect/Confirm).
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        return dlg

    def _alert(self, title: str, message: str, icon: str = "⚠️") -> None:
        """Show a short modal notice with a single dismiss button."""
        dlg = self._make_dialog(title, 360, 190)
        dialog_header(dlg, title, icon=icon, subtitle=message, size=15,
                      big_icon=True, pady=(16, 12))
        ok = button_row(
            dlg, [{"name": "ok", "text": t("OK"), "command": dlg.destroy,
                   "width": 120, "fg_color": ACCENT,
                   "hover_color": ACCENT_HOVER,
                   "text_color": TEXT_ON_ACCENT, "expand": False}],
            padx=110, pady=(0, 14), height=34)["ok"]
        dlg.bind("<Return>", lambda _e: dlg.destroy())
        ok.focus()

    def _confirm(self, title: str, message: str, *, icon: str,
                 confirm_text: str, on_confirm,
                 window_title: str | None = None,
                 size: tuple = (360, 190), big_icon: bool = False,
                 parent=None) -> ctk.CTkToplevel:
        """Modal yes/no for a destructive action.

        Five dialogs carried their own copy of this — two of them building
        the toplevel by hand and taking the grab through a second, parallel
        mechanism, so they never appeared in `_grab_stack`. The shared rules
        live here: Enter cancels, Cancel takes focus, and the confirming
        button is never reachable by keyboard alone.
        """
        width, height = size
        dlg = self._make_dialog(window_title or title, width, height)
        title, message = t(title), t(message)
        confirm_text = t(confirm_text)
        dialog_header(dlg, title, icon=icon, subtitle=message, size=15,
                      big_icon=big_icon,
                      pady=(16 if big_icon else 20, 14))

        def confirm():
            on_confirm(dlg)

        made = button_row(dlg, [
            {"name": "confirm", "text": confirm_text, "command": confirm,
             "side": "left", "fg_color": RED, "hover_color": RED_HOVER,
             "text_color": TEXT_ON_ACCENT},
            {"name": "cancel", "text": "Cancel", "command": dlg.destroy,
             "side": "right", "fg_color": BG_TERT,
             "hover_color": CARD_HOVER},
        ])
        # Enter cancels: a destructive action takes a deliberate click, and
        # a dialog that appears under the user's hands must not be able to
        # confirm itself on a keypress already in flight.
        dlg.bind("<Return>", lambda _e: dlg.destroy())
        made["cancel"].focus()
        return dlg

    def _save_guarded(self) -> bool:
        """Write the vault, reporting failure instead of raising.

        Returns True on success. A write can fail on a full or read-only
        disk; letting the exception escape a Tk callback left the change
        applied in memory with nothing on screen to say it was never
        persisted. On failure the change is queued so the next flush — on
        lock, minimize or quit — retries it.
        """
        try:
            save_data(self.data, self.key)
        except (OSError, ValueError, TypeError) as exc:
            log.error("Save failed: %s", exc, exc_info=True)
            self._save_pending = True
            self._save_failure_reported = True
            self._alert(
                "Could not save",
                t("The vault file could not be written, so this change "
                  "is only in memory for now.\n\n{error}", error=exc))
            return False
        self._save_failure_reported = False
        return True

    def _open_url(self, url: str) -> None:
        """Open *url* in the browser, refusing any non-http(s) scheme."""
        target = safe_url(url)
        if not target:
            log.warning("Refused to open unsafe URL scheme.")
            self._alert(
                "Link blocked",
                "This entry's link is not an http or https address, so it "
                "was not opened.")
            return
        try:
            webbrowser.open(target)
        except OSError as exc:
            log.error("Opening the browser failed: %s", exc, exc_info=True)
            self._alert("Could not open browser", str(exc))

    def _copy_to_clipboard(self, text: str, btn=None,
                            force_clear_seconds: int | None = None) -> None:
        """Copy *text* to clipboard with auto-clear scheduling.

        If *btn* is provided, flash a '✅ Done!' confirmation on it.
        If *force_clear_seconds* is set, override the user setting (used by
        SSH/RDP flows that briefly stage the password for paste).
        """
        try:
            pyperclip.copy(text)
        except (OSError, RuntimeError, pyperclip.PyperclipException) as exc:
            # No clipboard backend: a copy button must not take the app down.
            log.error("Clipboard copy failed: %s", exc)
            self._alert("Clipboard unavailable",
                        "This system has no working clipboard, so nothing "
                        "was copied.")
            return
        if btn:
            orig = btn.cget("text")
            orig_fg = btn.cget("fg_color")
            btn.configure(text=t("✅ Done!"), fg_color=GREEN)
            self.root.after(
                1000, lambda: safe_cfg(btn, orig, orig_fg))
        clear_sec = (force_clear_seconds
                     if force_clear_seconds is not None
                     else self.settings.get("clipboard_clear_seconds", 30))
        if clear_sec > 0:
            if self._clipboard_timer:
                self.root.after_cancel(self._clipboard_timer)
            # Only the digest is kept, so the timer never holds a second
            # plaintext copy of the secret.
            self._clipboard_digest = password_hash(text) if text else None
            self._clipboard_timer = self.root.after(
                clear_sec * 1000, self._clear_clipboard)

    def run(self):

        if (self.settings.get("start_minimized", False)
                and os.path.exists(DATA_FILE)):
            self.root.after(200, self.minimize_to_widget)
        self.root.mainloop()


if __name__ == "__main__":
    if not instance_lock.acquire():
        # A second copy would load its own snapshot of the vault and write it
        # back in full, discarding whatever the first one saved meanwhile.
        log.info("Another instance is already running; focusing it.")
        instance_lock.focus_existing()
        sys.exit(0)
    PasswordVault().run()

