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
# Journal for an in-flight salt rotation; see begin_rotation().
ROTATION_FILE = os.path.join(DATA_DIR, "vault.salt.pending")
APP_DIR = _EXE_DIR

# Upper bound for files we are willing to read into memory. A real vault is
# a few hundred KB; anything at this scale is corruption or a hostile file.
MAX_VAULT_BYTES = 64 * 1024 * 1024


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


def read_salt() -> bytes | None:
    """Return the stored salt, or None when no vault has been created yet.

    Unlike :func:`get_or_create_salt` this never writes, so a caller that
    has to undo a rotation can capture the previous value first.
    """
    try:
        with open(SALT_FILE, "rb") as f:
            return f.read()
    except OSError:
        return None


def begin_rotation(new_salt: bytes) -> None:
    """Record the salt a rotation is about to switch to.

    Changing the master password writes the vault under the new key and
    then rotates the salt. Between those two writes the file on disk and
    the salt on disk disagree, and if the rotation fails *and* the rollback
    re-save also fails, nothing on disk says which key the ciphertext is
    under — the vault becomes unopenable by any password.

    The journal closes that window. It costs one 32-byte write before the
    re-encryption starts, and :func:`candidate_salts` hands both salts to
    the login screen so whichever one matches wins.
    """
    tmp = ROTATION_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(new_salt)
    os.replace(tmp, ROTATION_FILE)
    _restrict_file(ROTATION_FILE)
    log.info("Salt rotation journalled.")


def end_rotation() -> None:
    """Clear the journal once the salt and the vault agree again."""
    try:
        os.remove(ROTATION_FILE)
    except FileNotFoundError:
        pass
    except OSError as exc:
        # A stale journal is harmless: it only ever adds one extra key to
        # try at unlock, and the next successful rotation overwrites it.
        log.warning("Could not clear the rotation journal: %s", exc)


def candidate_salts() -> list[bytes]:
    """Every salt the vault might currently be encrypted under.

    Normally one. After an interrupted master-password change, also the
    salt that rotation was heading for, so a vault written under the new
    key is still reachable with the new password.
    """
    salts = []
    current = read_salt()
    if current:
        salts.append(current)
    try:
        with open(ROTATION_FILE, "rb") as f:
            pending = f.read()
    except OSError:
        return salts
    if pending and pending not in salts:
        log.warning("An interrupted salt rotation was found; the pending "
                    "salt will also be tried at unlock.")
        salts.append(pending)
    return salts


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
    size = os.path.getsize(DATA_FILE)
    if size > MAX_VAULT_BYTES:
        log.error("Vault file is implausibly large (%d bytes); refusing to "
                  "load.", size)
        raise ValueError("Vault file is too large to be valid.")
    with open(DATA_FILE, "rb") as f:
        raw = decrypt_data(f.read(), key)
    # The ciphertext is authenticated, so this only guards against a vault
    # written by a different version or a bug — not against tampering.
    data = normalize_vault(raw)
    # normalize_vault fills the container keys in, so ask the raw payload
    # whether this load is actually a structural upgrade.
    schema_changed = (not isinstance(raw, dict)
                      or "trash" not in raw
                      or "categories" not in raw)
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

    # Auto-clean trash older than TRASH_DAYS. This is applied to the
    # in-memory copy only: the filter runs on every load anyway, so writing
    # it back would re-encrypt the whole vault at every startup for no
    # observable gain. The next user-initiated save persists it.
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(days=TRASH_DAYS)).isoformat()
    data["trash"] = [t for t in data["trash"]
                     if t.get("deleted_at", "") > cutoff]

    if schema_changed:
        save_data(data, key)
    return data


# ─── Encrypted Backup ────────────────────────────────────────
# Self-contained backup file format (JSON, UTF-8). The backup carries
# its own salt — it is independent of vault.salt — so that the user
# can restore on any machine. KDF parameters are recorded inline so
# future PBKDF2 iteration bumps don't break old backups.
#
# {
#   "format": "PasswordVault-Backup",
#   "version": 1,
#   "kdf": "pbkdf2-sha256",
#   "iterations": 480000,
#   "salt": "<base64>",
#   "ciphertext": "<base64 fernet token>"
# }

BACKUP_FORMAT = "PasswordVault-Backup"
BACKUP_VERSION = 1

# Default category list, used when a backup predates the field or was
# hand-edited without it.
DEFAULT_CATEGORIES = ["General", "Social", "Work", "Banking"]


def normalize_vault(data) -> dict:
    """Return *data* as a usable vault dict, or raise ``ValueError``.

    A decrypted backup is only as trustworthy as the file it came from: a
    hand-edited or truncated one can decrypt cleanly and still be the wrong
    shape. Restoring used to assign it straight onto the live vault, so the
    mismatch only surfaced later as a ``KeyError`` in the UI — after the
    file had been written and, at login, after the salt had been rotated.
    """
    if not isinstance(data, dict):
        raise ValueError("Backup does not contain a vault.")
    entries = data.get("entries", [])
    if not isinstance(entries, list) or not all(
            isinstance(e, dict) for e in entries):
        raise ValueError("Backup has a malformed entry list.")
    categories = data.get("categories")
    if not isinstance(categories, list) or not all(
            isinstance(c, str) for c in categories):
        categories = list(DEFAULT_CATEGORIES)
    trash = data.get("trash")
    if not isinstance(trash, list) or not all(
            isinstance(t, dict) for t in trash):
        trash = []
    clean = dict(data)
    clean["entries"] = entries
    clean["categories"] = categories
    clean["trash"] = trash
    return clean


def export_encrypted_backup(data: dict, backup_password: str,
                              filepath: str) -> None:
    """Encrypt *data* with a key derived from *backup_password* and write
    a portable JSON backup file at *filepath*.

    The backup uses a fresh salt and is fully self-describing, so the
    user can restore on a clean machine with only the backup file and
    the backup password.
    """
    if not backup_password:
        raise ValueError("Backup password is required.")

    salt = os.urandom(32)
    iterations = 480000
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                      salt=salt, iterations=iterations)
    key = base64.urlsafe_b64encode(kdf.derive(backup_password.encode()))
    token = Fernet(key).encrypt(
        json.dumps(data, ensure_ascii=False).encode())

    payload = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "kdf": "pbkdf2-sha256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": token.decode("ascii"),
    }
    tmp = filepath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, filepath)
        log.info("Encrypted backup written to %s.", filepath)
    except (OSError, ValueError) as exc:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        log.error("Failed to write encrypted backup: %s", exc, exc_info=True)
        raise


def import_encrypted_backup(filepath: str,
                              backup_password: str) -> dict:
    """Read and decrypt a backup file produced by export_encrypted_backup.

    Raises:
        ValueError if the file is not a recognized backup or the
        password is wrong.
    """
    # The user picks this file, so treat it like any other untrusted input:
    # a real backup is a few hundred KB, and json.load would otherwise pull
    # an arbitrarily large file into memory before rejecting it.
    size = os.path.getsize(filepath)
    if size > MAX_VAULT_BYTES:
        log.error("Backup file is implausibly large (%d bytes); refusing to "
                  "read.", size)
        raise ValueError("Backup file is too large to be valid.")
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            payload = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError("Not a valid backup file.") from exc

    if payload.get("format") != BACKUP_FORMAT:
        raise ValueError("Not a Password Vault backup file.")
    version = payload.get("version")
    if version != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {version}")
    if payload.get("kdf") != "pbkdf2-sha256":
        raise ValueError(f"Unsupported KDF: {payload.get('kdf')}")

    try:
        salt = base64.b64decode(payload["salt"])
        token = payload["ciphertext"].encode("ascii")
        iterations = int(payload["iterations"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Backup file is malformed.") from exc

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                      salt=salt, iterations=iterations)
    key = base64.urlsafe_b64encode(kdf.derive(backup_password.encode()))
    try:
        plaintext = Fernet(key).decrypt(token)
    except Exception as exc:
        # Wrong password OR tampered ciphertext — same opaque error
        # so we don't leak which.
        raise ValueError("Wrong password or corrupted backup.") from exc
    try:
        payload = json.loads(plaintext.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Backup contents are not readable.") from exc
    return normalize_vault(payload)

