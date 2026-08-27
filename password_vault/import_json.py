"""Importing Bitwarden's JSON export.

A CSV column map cannot express this format. Bitwarden's JSON keeps folders
as a separate list joined by id, allows several URIs per item, carries typed
items beyond logins (secure notes, cards, identities), and gives each item
its own list of custom fields. Flattening that into columns is what the CSV
export already does, lossily — reading the JSON keeps what the CSV drops.

Same rule as the CSV profiles: anything this app has no home for is written
into the entry's notes under its own name rather than dropped. Item types
that are not logins are imported as notes-only entries, because a secure
note with no password is still the user's data and silently skipping it
would be the worst outcome.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("PasswordVault")

# Bitwarden's numeric item types.
TYPE_LOGIN = 1
TYPE_SECURE_NOTE = 2
TYPE_CARD = 3
TYPE_IDENTITY = 4

TYPE_NAMES = {
    TYPE_LOGIN: "Login",
    TYPE_SECURE_NOTE: "Secure note",
    TYPE_CARD: "Card",
    TYPE_IDENTITY: "Identity",
}

# Card and identity fields, in the order they read naturally. Bitwarden has
# no password field for these, so they land in the notes.
CARD_FIELDS = [
    ("cardholderName", "Cardholder"),
    ("brand", "Brand"),
    ("number", "Number"),
    ("expMonth", "Expiry month"),
    ("expYear", "Expiry year"),
    ("code", "Security code"),
]

IDENTITY_FIELDS = [
    ("title", "Title"), ("firstName", "First name"),
    ("middleName", "Middle name"), ("lastName", "Last name"),
    ("username", "Username"), ("company", "Company"),
    ("ssn", "SSN"), ("passportNumber", "Passport"),
    ("licenseNumber", "Licence"), ("email", "Email"),
    ("phone", "Phone"), ("address1", "Address"),
    ("address2", "Address 2"), ("address3", "Address 3"),
    ("city", "City"), ("state", "State"),
    ("postalCode", "Postal code"), ("country", "Country"),
]


def looks_like_bitwarden_json(payload) -> bool:
    """True when *payload* is a Bitwarden export rather than some other JSON."""
    if not isinstance(payload, dict):
        return False
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    if not items:
        # An empty export is still recognisable by its envelope.
        return "folders" in payload or "encrypted" in payload
    return any(isinstance(item, dict) and "type" in item for item in items)


def is_encrypted_export(payload) -> bool:
    """Bitwarden can export a password-protected file this cannot read."""
    return bool(isinstance(payload, dict) and payload.get("encrypted"))


def _folder_names(payload) -> dict[str, str]:
    names = {}
    for folder in payload.get("folders") or []:
        if isinstance(folder, dict) and folder.get("id"):
            names[folder["id"]] = str(folder.get("name") or "")
    return names


def _note_lines(item: dict) -> list[str]:
    """Everything about *item* that has no dedicated field here."""
    lines = []
    item_type = item.get("type")

    if item_type == TYPE_CARD:
        for key, label in CARD_FIELDS:
            value = (item.get("card") or {}).get(key)
            if value not in (None, ""):
                lines.append(f"{label}: {value}")
    elif item_type == TYPE_IDENTITY:
        for key, label in IDENTITY_FIELDS:
            value = (item.get("identity") or {}).get(key)
            if value not in (None, ""):
                lines.append(f"{label}: {value}")

    login = item.get("login") or {}
    if login.get("totp"):
        lines.append(f"TOTP: {login['totp']}")

    # Every URI after the first, which becomes the entry's URL.
    uris = [u.get("uri") for u in (login.get("uris") or [])
            if isinstance(u, dict) and u.get("uri")]
    for extra in uris[1:]:
        lines.append(f"Also: {extra}")

    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name") or "Field"
        value = field.get("value")
        if value not in (None, ""):
            lines.append(f"{name}: {value}")

    if item.get("attachments"):
        # A JSON export references attachments but does not contain them.
        count = len(item["attachments"])
        lines.append(f"({count} attachment(s) not included in the export)")

    return lines


def parse_items(payload) -> list[dict]:
    """Convert a decoded Bitwarden export into entry dicts."""
    if is_encrypted_export(payload):
        raise ValueError(
            "This Bitwarden export is password-protected. Export again "
            "with encryption turned off, or use the CSV export.")
    if not looks_like_bitwarden_json(payload):
        raise ValueError("Not a Bitwarden JSON export.")

    folders = _folder_names(payload)
    entries = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        login = item.get("login") or {}
        uris = [u.get("uri") for u in (login.get("uris") or [])
                if isinstance(u, dict) and u.get("uri")]

        notes = str(item.get("notes") or "")
        extra = _note_lines(item)
        item_type = item.get("type")
        if item_type != TYPE_LOGIN:
            # Say what it was, so a card in the vault is not a mystery.
            extra.insert(0, f"Item type: "
                            f"{TYPE_NAMES.get(item_type, item_type)}")
        if extra:
            notes = "\n".join(([notes] if notes else []) + extra)

        category = folders.get(item.get("folderId") or "", "") or "General"
        entries.append({
            "title": str(item.get("name") or ""),
            "username": str(login.get("username") or ""),
            "password": str(login.get("password") or ""),
            "url": str(uris[0]) if uris else "",
            "category": category,
            "notes": notes,
            "pinned": bool(item.get("favorite")),
        })
    return entries


def load(filepath: str) -> list[dict]:
    """Read and parse a Bitwarden JSON export."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        try:
            payload = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError("Not a readable JSON file.") from exc
    entries = parse_items(payload)
    log.info("Parsed %d items from a Bitwarden JSON export.", len(entries))
    return entries
