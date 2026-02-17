"""
🔐 Password Vault - Modern password manager for Windows (Apple Dark Style)
"""

import logging
import os

APP_VERSION = "3.1"
APP_AUTHOR = "Eslam Atwa"

# ─── Logging (initialized once at package import) ─────────────
_LOG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "PasswordVault")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "vault.log")

logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)

