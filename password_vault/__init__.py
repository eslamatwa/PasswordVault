"""
🔐 Password Vault - Modern password manager for Windows (Apple Dark Style)
"""

import logging
import logging.handlers
import os

APP_VERSION = "3.4"
APP_AUTHOR = "Eslam Atwa"

# ─── Logging (initialized once at package import) ─────────────
_LOG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "PasswordVault")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "vault.log")

# Rotating handler: 1 MB per file, keep 3 backups (max ~4 MB total).
_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=1_048_576, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"))
_root = logging.getLogger()
if not any(isinstance(h, logging.handlers.RotatingFileHandler)
           for h in _root.handlers):
    _root.addHandler(_handler)
_root.setLevel(logging.INFO)

