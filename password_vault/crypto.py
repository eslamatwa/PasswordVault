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
import stat
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


def _restrict_file(path: str) -> None:
    """Set restrictive permissions on *path* (owner read/write only)."""
    try:
        if sys.platform == "win32":
            # On Windows: remove inherited ACLs, keep owner only.
            # If USERNAME is missing for any reason, skip the icacls call —
            # an empty user spec would not grant anyone access (icacls would
            # fail), but explicit guard avoids any unexpected behavior.
            user = os.environ.get("USERNAME", "")
            if not user:
                log.warning("USERNAME env var missing; skipping ACL restrict.")
                return
            import subprocess as _sp
            _sp.run(
                ["icacls", path, "/inheritance:r",
                 "/grant:r", f"{user}:F"],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                check=False, capture_output=True,
            )
        else:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


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
    _restrict_file(SALT_FILE)
    log.info("New salt generated (%d bytes).", len(salt))
    return salt


def rotate_salt(salt: bytes | None = None) -> bytes:
    """Atomically replace the salt file.

    If *salt* is None, generate a new 32-byte salt. Otherwise persist the
    given salt (caller is responsible for using a CSPRNG).

    Used when the master password changes — re-deriving the key with a
    fresh salt prevents an attacker who captured the old vault file from
    accelerating attacks against the new password using precomputed
    PBKDF2 work bound to the old salt.
    """
    if salt is None:
        salt = os.urandom(32)
    tmp = SALT_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(salt)
    os.replace(tmp, SALT_FILE)
    _restrict_file(SALT_FILE)
    log.info("Salt rotated (new %d bytes).", len(salt))
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
        _restrict_file(DATA_FILE)
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
    schema_changed = False  # only true for structural upgrades, not trash GC
    now_iso = datetime.datetime.now().isoformat()
    for entry in data.get("entries", []):
        if "id" not in entry:
            entry["id"] = str(uuid.uuid4())
            schema_changed = True
        if "created_at" not in entry:
            entry["created_at"] = now_iso
            schema_changed = True
        if "modified_at" not in entry:
            entry["modified_at"] = now_iso
            schema_changed = True
        if "url" not in entry:
            entry["url"] = ""
            schema_changed = True
        if "pinned" not in entry:
            entry["pinned"] = False
            schema_changed = True
    if "trash" not in data:
        data["trash"] = []
        schema_changed = True

    # Take a one-time backup before the first schema migration overwrites
    # the original ciphertext.
    if schema_changed:
        backup_path = DATA_FILE + ".pre-migration.bak"
        if not os.path.exists(backup_path):
            try:
                shutil.copy2(DATA_FILE, backup_path)
                _restrict_file(backup_path)
                log.info("Pre-migration backup created at %s.", backup_path)
            except OSError as exc:
                log.warning("Pre-migration backup failed: %s", exc)

    # Auto-clean trash older than TRASH_DAYS
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(days=TRASH_DAYS)).isoformat()
    before = len(data["trash"])
    data["trash"] = [t for t in data["trash"]
                     if t.get("deleted_at", "") > cutoff]
    trash_changed = len(data["trash"]) != before

    if schema_changed or trash_changed:
        save_data(data, key)
    return data

