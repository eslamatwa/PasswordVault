"""
Settings persistence — load / save user preferences.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("PasswordVault")

# ─── Paths ────────────────────────────────────────────────────
_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
DATA_DIR = os.path.join(_APPDATA, "PasswordVault")
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# ─── Constants ────────────────────────────────────────────────
AUTO_LOCK_MINUTES = 5
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
TRASH_DAYS = 30
PASSWORD_AGE_WARNING = 90

# Appearance modes, in the order they appear in Settings.
THEME_MODES = ("System", "Dark", "Light")

# Interface languages. Kept here rather than imported from i18n so that
# settings stays free of UI imports and can be loaded before anything else.
LANGUAGE_CODES = ("English", "Arabic")

DEFAULT_SETTINGS: dict = {
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
    "clipboard_clear_seconds": 30,
    # An SSH client the user pointed at by hand. Detection covers the
    # usual installs; this is for a portable copy, a KiTTY, or anything
    # that lives somewhere no fixed path would guess.
    "ssh_client_path": "",
    "theme": "Dark",
    "language": "English",
    # Whether the "there is no recovery" prompt has been shown, and
    # when a backup was last written. A vault with no backup and a
    # forgotten master password cannot be opened by anyone, so the
    # app has to say so once rather than leave it in a menu.
    "backup_prompted": False,
    "last_backup_at": "",
    # Brute-force state, persisted so closing and reopening the app does
    # not hand an attacker a fresh set of attempts. It lives here rather
    # than in the vault because it has to be readable while locked.
    "failed_streak": 0,
    "lockout_until": 0,
}

# Ceiling for a stored lockout deadline, in seconds from now. A saved
# absolute timestamp cannot be trusted on its own: moving the system clock
# forward and back would otherwise leave the vault locked for years.
MAX_LOCKOUT_HORIZON = 1800

# key -> (expected type, extra check or None). Anything not listed here is
# not a setting this version understands.
_SPEC: dict[str, tuple] = {
    "auto_lock_minutes": (int, lambda v: 0 <= v <= 24 * 60),
    "gen_length": (int, lambda v: 4 <= v <= 128),
    "gen_upper": (bool, None),
    "gen_lower": (bool, None),
    "gen_digits": (bool, None),
    "gen_symbols": (bool, None),
    "start_minimized": (bool, None),
    "default_card_color": (str, lambda v: bool(v) and len(v) <= 32),
    "max_login_attempts": (int, lambda v: 1 <= v <= 100),
    "lockout_seconds": (int, lambda v: 0 <= v <= 24 * 3600),
    "clipboard_clear_seconds": (int, lambda v: 0 <= v <= 3600),
    # Not checked for existence here: settings are read while the vault
    # is still locked, and a path on a drive that is not mounted yet
    # should not be silently forgotten. Detection checks the file when
    # it actually needs it.
    "ssh_client_path": (str, lambda v: len(v) <= 512),
    "theme": (str, lambda v: v in THEME_MODES),
    "language": (str, lambda v: v in LANGUAGE_CODES),
    "backup_prompted": (bool, None),
    "last_backup_at": (str, lambda v: len(v) <= 40),
    "failed_streak": (int, lambda v: 0 <= v <= 100000),
    "lockout_until": (int, lambda v: v >= 0),
}


def _accepted(saved: dict) -> dict:
    """Keep only the stored values that match their expected type and range.

    Saved settings used to be merged blindly, so a corrupted or hand-edited
    file could put a string into ``auto_lock_minutes``; that value then
    reached ``after()`` and broke the idle timer at runtime.
    """
    clean: dict = {}
    for key, value in saved.items():
        spec = _SPEC.get(key)
        if spec is None:
            log.warning("Ignoring unknown setting %r.", key)
            continue
        expected, extra_check = spec
        if expected is bool:
            ok = isinstance(value, bool)
        elif expected is int:
            # bool is an int subclass, but "true" is not a duration.
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = isinstance(value, expected)
        if ok and extra_check is not None:
            ok = extra_check(value)
        if ok:
            clean[key] = value
        else:
            log.warning("Ignoring out-of-range value for setting %r.", key)
    return clean


def load_settings() -> dict:
    """Load user settings from disk, merged over the defaults."""
    merged = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load settings: %s", exc)
            return merged
        if not isinstance(saved, dict):
            log.warning("Settings file is not an object; using defaults.")
            return merged
        merged.update(_accepted(saved))
    return merged


def save_settings(settings: dict) -> None:
    """Persist user settings to disk (atomic write)."""
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_FILE)
    except (OSError, TypeError, ValueError) as exc:
        log.error("Failed to save settings: %s", exc)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

