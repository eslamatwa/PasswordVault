"""Importing 1Password's 1PUX export.

A 1PUX file is a zip. Inside it, ``export.data`` is JSON describing every
account, every vault in it, and every item in those — and ``files/`` holds
the attachments. None of that fits a CSV column map, which is why
1Password's own CSV export drops most of it.

Two decisions, both following what the Bitwarden JSON reader already does:

**Nothing is skipped for being the wrong type.** 1Password stores logins,
secure notes, cards, identities, software licences and more. Only a login
has a password, so a reader that wanted one would silently discard the
rest of someone's vault. Everything is imported; anything without a
password arrives as a notes-only entry with its type recorded.

**Attachments are named, not extracted.** This app stores no files, so
there is nowhere for them to go. Writing them out beside the vault would
put decrypted documents on disk next to an encrypted one, which is the
opposite of the point. The entry's notes list what was attached and say
the files are still in the .1pux — so nothing is lost silently, and the
user knows where to look.
"""

from __future__ import annotations

import json
import logging
import zipfile

log = logging.getLogger("PasswordVault")

EXPORT_MEMBER = "export.data"

# An export larger than this is not a password vault.
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
# The uncompressed size of export.data we are willing to read. A zip can
# claim to be small and expand to gigabytes.
MAX_EXPORT_BYTES = 64 * 1024 * 1024

# 1Password's category ids, for the ones worth naming in a note.
CATEGORY_NAMES = {
    "001": "Login",
    "002": "Credit card",
    "003": "Secure note",
    "004": "Identity",
    "005": "Password",
    "006": "Document",
    "100": "Software licence",
    "101": "Bank account",
    "102": "Database",
    "103": "Driver licence",
    "104": "Outdoor licence",
    "105": "Membership",
    "106": "Passport",
    "107": "Rewards programme",
    "108": "Social security number",
    "109": "Wireless router",
    "110": "Server",
    "111": "Email account",
}

LOGIN_CATEGORY = "001"


def _field_value(field) -> str:
    """1PUX wraps a field's value in a one-key object naming its type."""
    value = field.get("value")
    if isinstance(value, dict):
        for key in ("string", "concealed", "email", "phone", "url",
                    "totp", "date", "monthYear", "creditCardNumber",
                    "creditCardType", "gender", "menu", "file"):
            if key in value and value[key] not in (None, ""):
                inner = value[key]
                if isinstance(inner, dict):
                    # A file field points at an attachment.
                    return str(inner.get("fileName") or "")
                return str(inner)
        return ""
    return "" if value is None else str(value)


def _login_fields(details) -> tuple[str, str]:
    """Username and password, by 1Password's own designation."""
    username = password = ""
    for field in details.get("loginFields") or []:
        if not isinstance(field, dict):
            continue
        designation = field.get("designation")
        if designation == "username" and not username:
            username = str(field.get("value") or "")
        elif designation == "password" and not password:
            password = str(field.get("value") or "")
    return username, password


def _section_lines(details) -> list[str]:
    """Custom sections, which is where 1Password keeps everything else."""
    lines = []
    for section in details.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("title") or "").strip()
        for field in section.get("fields") or []:
            if not isinstance(field, dict):
                continue
            value = _field_value(field)
            if not value:
                continue
            name = str(field.get("title") or "Field").strip() or "Field"
            lines.append(f"{heading}: {name}: {value}" if heading
                         else f"{name}: {value}")
    return lines


def _item_entry(item, vault_name) -> dict | None:
    """One 1PUX item as an entry dict, or None if it is not one."""
    if not isinstance(item, dict):
        return None
    if item.get("state") == "archived":
        # Archived items are still the user's data, but they are not what
        # someone importing a working vault is asking for.
        return None

    overview = item.get("overview") or {}
    details = item.get("details") or {}
    category = str(item.get("categoryUuid") or "")

    username, password = _login_fields(details)

    urls = [u.get("url") for u in (overview.get("urls") or [])
            if isinstance(u, dict) and u.get("url")]
    primary = overview.get("url") or (urls[0] if urls else "")

    notes = str(details.get("notesPlain") or "")
    extra = []
    if category and category != LOGIN_CATEGORY:
        extra.append(f"Item type: "
                     f"{CATEGORY_NAMES.get(category, category)}")
    if not password and details.get("password"):
        # The standalone Password category keeps it outside loginFields.
        password = str(details["password"])
    extra.extend(_section_lines(details))
    for other in urls:
        if other != primary:
            extra.append(f"Also: {other}")

    attachments = [
        str(f.get("fileName") or "")
        for f in (details.get("documentAttributes") or {},)
        if isinstance(f, dict) and f.get("fileName")]
    for section in details.get("sections") or []:
        for field in (section.get("fields") or []
                      if isinstance(section, dict) else []):
            value = field.get("value") if isinstance(field, dict) else None
            if isinstance(value, dict) and isinstance(value.get("file"),
                                                      dict):
                name = value["file"].get("fileName")
                if name:
                    attachments.append(str(name))
    if attachments:
        extra.append("Attachments (still in the .1pux file): "
                     + ", ".join(attachments))

    if extra:
        notes = "\n".join(([notes] if notes else []) + extra)

    title = str(overview.get("title") or "")
    if not (title or password or notes):
        return None

    tags = overview.get("tags") or []
    category_name = (str(tags[0]) if tags and isinstance(tags[0], str)
                     else vault_name)

    return {
        "title": title,
        "username": username,
        "password": password,
        "url": str(primary or ""),
        "category": category_name or "General",
        "notes": notes,
        "pinned": bool(item.get("favIndex")),
    }


def parse_export(payload) -> list[dict]:
    """Convert a decoded ``export.data`` into entry dicts."""
    if not isinstance(payload, dict) or "accounts" not in payload:
        raise ValueError("Not a 1Password 1PUX export.")

    entries = []
    for account in payload.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        for vault in account.get("vaults") or []:
            if not isinstance(vault, dict):
                continue
            vault_name = str(
                (vault.get("attrs") or {}).get("name") or "").strip()
            for wrapper in vault.get("items") or []:
                if not isinstance(wrapper, dict):
                    continue
                entry = _item_entry(wrapper.get("item"), vault_name)
                if entry is not None:
                    entries.append(entry)
    return entries


def looks_like_1pux(path: str) -> bool:
    """True when *path* is a zip holding a 1PUX export."""
    try:
        with zipfile.ZipFile(path) as archive:
            return EXPORT_MEMBER in archive.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def load(filepath: str) -> list[dict]:
    """Read and parse a 1PUX archive."""
    import os

    size = os.path.getsize(filepath)
    if size > MAX_ARCHIVE_BYTES:
        raise ValueError("This export is too large to be a password vault.")

    try:
        archive = zipfile.ZipFile(filepath)
    except zipfile.BadZipFile as exc:
        raise ValueError("Not a readable .1pux file.") from exc

    with archive:
        if EXPORT_MEMBER not in archive.namelist():
            raise ValueError(
                "This zip does not contain a 1Password export.")
        info = archive.getinfo(EXPORT_MEMBER)
        # A zip can claim to be small and expand to gigabytes.
        if info.file_size > MAX_EXPORT_BYTES:
            raise ValueError("The export inside this file is too large.")
        raw = archive.read(EXPORT_MEMBER)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The export inside this file is not readable.") \
            from exc

    entries = parse_export(payload)
    log.info("Parsed %d items from a 1PUX export.", len(entries))
    return entries
