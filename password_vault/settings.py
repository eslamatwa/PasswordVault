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
}


def load_settings() -> dict:
    """Load user settings from disk, merged with defaults."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(saved)
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load settings: %s", exc)
    return dict(DEFAULT_SETTINGS)


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

