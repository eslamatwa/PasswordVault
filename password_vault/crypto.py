"""
Encryption, key derivation, and vault data persistence.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import shutil
import sys
import uuid

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .settings import DATA_DIR, TRASH_DAYS

log = logging.getLogger("PasswordVault")

# ─── Paths ────────────────────────────────────────────────────
_EXE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))

# Migrate legacy files from exe dir → AppData
for _fname in ("vault.dat", "vault.salt"):
    _old = os.path.join(_EXE_DIR, _fname)
    _new = os.path.join(DATA_DIR, _fname)
    if os.path.exists(_old) and not os.path.exists(_new):
        shutil.copy2(_old, _new)

DATA_FILE = os.path.join(DATA_DIR, "vault.dat")
SALT_FILE = os.path.join(DATA_DIR, "vault.salt")
APP_DIR = _EXE_DIR


# ─── Salt ─────────────────────────────────────────────────────
def get_or_create_salt() -> bytes:
    """Load existing salt or create a new 32-byte salt.
    Backwards-compatible: existing 16-byte salts are kept as-is."""
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, "rb") as f:
            return f.read()
    salt = os.urandom(32)
    with open(SALT_FILE, "wb") as f:
        f.write(salt)
    log.info("New salt generated (%d bytes).", len(salt))
    return salt


# ─── Key Derivation ──────────────────────────────────────────
def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from *password* + *salt*."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                      salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


# ─── Encrypt / Decrypt ───────────────────────────────────────
def encrypt_data(data: dict, key: bytes) -> bytes:
    """Serialize *data* to JSON and encrypt with *key*."""
    return Fernet(key).encrypt(json.dumps(data, ensure_ascii=False).encode())


def decrypt_data(token: bytes, key: bytes) -> dict:
    """Decrypt *token* with *key* and deserialize JSON."""
    return json.loads(Fernet(key).decrypt(token).decode())


# ─── Save / Load ─────────────────────────────────────────────
def save_data(data: dict, key: bytes) -> None:
    """Encrypt and atomically write *data* to disk."""
    tmp = DATA_FILE + ".tmp"
    try:
        encrypted = encrypt_data(data, key)
        with open(tmp, "wb") as f:
            f.write(encrypted)
        os.replace(tmp, DATA_FILE)
        log.info("Vault data saved successfully.")
    except (OSError, ValueError, TypeError) as exc:
        log.error("Failed to save vault data: %s", exc, exc_info=True)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_data(key: bytes) -> dict:
    """Decrypt and return vault data (creates default structure if new)."""
    if not os.path.exists(DATA_FILE):
        return {"categories": ["General", "Social", "Work", "Banking"],
                "entries": [], "trash": []}
    with open(DATA_FILE, "rb") as f:
        data = decrypt_data(f.read(), key)
    changed = False
    now_iso = datetime.datetime.now().isoformat()
    for entry in data.get("entries", []):
        if "id" not in entry:
            entry["id"] = str(uuid.uuid4())
            changed = True
        if "created_at" not in entry:
            entry["created_at"] = now_iso
            changed = True
        if "modified_at" not in entry:
            entry["modified_at"] = now_iso
            changed = True
        if "url" not in entry:
            entry["url"] = ""
            changed = True
        if "pinned" not in entry:
            entry["pinned"] = False
            changed = True
    if "trash" not in data:
        data["trash"] = []
        changed = True
    # Auto-clean trash older than TRASH_DAYS
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(days=TRASH_DAYS)).isoformat()
    before = len(data["trash"])
    data["trash"] = [t for t in data["trash"]
                     if t.get("deleted_at", "") > cutoff]
    if len(data["trash"]) != before:
        changed = True
    if changed:
        save_data(data, key)
    return data

