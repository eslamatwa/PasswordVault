"""Column maps for importing a vault exported by another password manager.

Import used to expect this app's own column layout and nothing else, so a
file from Chrome or Bitwarden produced a vault full of blank entries rather
than an error.

Two decisions are baked in here, both of which MVP.md left open:

**Detect, but show the answer.** A profile is guessed from the header row
and the guess is displayed in the import dialog, where the user can override
it. Asking first would put a question in front of every import, including
the overwhelmingly common case of re-importing this app's own export;
guessing silently would hide a wrong guess until after the rows landed.

**Nothing is dropped silently.** A TOTP secret is a credential, and a
custom field can be a recovery code — losing either without a word during
an import is worse than putting it somewhere imperfect. Columns this app
has no home for are appended to the entry's notes under their original
name. Attachments cannot be carried in a CSV at all, so a file that
references them keeps only the reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    """One source application's column layout.

    ``columns`` maps a lower-cased source header to one of this app's entry
    fields. ``extras`` maps a source header to the label its value is filed
    under in the notes. ``signature`` is the set of headers that identifies
    the format; detection scores a file by how much of it is present.
    """

    key: str
    label: str
    columns: dict[str, str]
    signature: frozenset[str]
    extras: dict[str, str] = field(default_factory=dict)

    def known_headers(self) -> frozenset[str]:
        return frozenset(self.columns) | frozenset(self.extras)


# This app's own export. Listed first so a re-import of our own file wins
# ties outright.
NATIVE = Profile(
    key="native",
    label="Password Vault",
    columns={
        "title": "title", "username": "username", "password": "password",
        "url": "url", "category": "category", "notes": "notes",
        "color": "color", "created": "created_at",
        "modified": "modified_at", "pinned": "pinned",
    },
    signature=frozenset({"title", "username", "password", "url",
                         "category", "color", "pinned"}),
)

CHROME = Profile(
    key="chrome",
    label="Chrome / Edge",
    columns={"name": "title", "url": "url", "username": "username",
             "password": "password", "note": "notes", "notes": "notes"},
    signature=frozenset({"name", "url", "username", "password"}),
)

FIREFOX = Profile(
    key="firefox",
    label="Firefox",
    columns={"url": "url", "username": "username", "password": "password"},
    signature=frozenset({"url", "username", "password", "httprealm",
                         "formactionorigin", "guid"}),
    extras={"httprealm": "HTTP realm"},
)

BITWARDEN = Profile(
    key="bitwarden",
    label="Bitwarden",
    columns={"name": "title", "notes": "notes", "folder": "category",
             "favorite": "pinned", "login_uri": "url",
             "login_username": "username", "login_password": "password"},
    signature=frozenset({"login_uri", "login_username", "login_password",
                         "folder", "name"}),
    # `type` and `reprompt` are export bookkeeping, not the user's data:
    # folding them in put "Item type: login" on the notes of every single
    # entry. They are reported as unmapped instead, so the import dialog
    # still names them rather than passing over them in silence.
    extras={"login_totp": "TOTP", "fields": "Custom fields"},
)

LASTPASS = Profile(
    key="lastpass",
    label="LastPass",
    columns={"name": "title", "url": "url", "username": "username",
             "password": "password", "extra": "notes",
             "grouping": "category", "fav": "pinned"},
    signature=frozenset({"url", "username", "password", "extra",
                         "grouping", "name"}),
    extras={"totp": "TOTP"},
)

ONEPASSWORD = Profile(
    key="1password",
    label="1Password",
    columns={"title": "title", "url": "url", "username": "username",
             "password": "password", "notes": "notes", "tags": "category",
             "favorite": "pinned"},
    signature=frozenset({"title", "url", "username", "password",
                         "otpauth", "tags"}),
    extras={"otpauth": "TOTP"},
)

KEEPASS = Profile(
    key="keepass",
    label="KeePass",
    columns={"account": "title", "login name": "username",
             "password": "password", "web site": "url",
             "comments": "notes", "group": "category"},
    signature=frozenset({"account", "login name", "password", "web site",
                         "comments"}),
)

PROFILES: tuple[Profile, ...] = (
    NATIVE, CHROME, BITWARDEN, LASTPASS, ONEPASSWORD, KEEPASS, FIREFOX,
)

BY_KEY = {p.key: p for p in PROFILES}

# A profile has to explain this much of its own signature before it is
# preferred over the native layout. Below it the file is more likely a
# hand-made sheet that happens to share a column name or two.
MIN_SIGNATURE_MATCH = 0.6


def normalize_headers(headers) -> list[str]:
    """Lower-case and trim a header row, keeping position."""
    return [str(h).strip().lower() if h is not None else ""
            for h in headers]


def score(profile: Profile, headers: list[str]) -> float:
    """Fraction of *profile*'s signature present in *headers*."""
    if not profile.signature:
        return 0.0
    present = profile.signature & frozenset(headers)
    return len(present) / len(profile.signature)


def detect(headers) -> Profile:
    """Return the profile that best explains *headers*.

    Ranked by how much of a profile's signature the file satisfies, then by
    how many columns that accounts for. The second term matters: Chrome's
    signature is a subset of LastPass's, so a LastPass file satisfies both
    completely and only specificity separates them.

    Falls back to the native layout, which is also what a file with an
    unrecognised header row is read as — the per-column lookup simply finds
    nothing and the rows are skipped as empty, rather than being silently
    mapped to the wrong fields.
    """
    normalized = normalize_headers(headers)
    present = frozenset(normalized)

    def rank(profile: Profile) -> tuple[float, int]:
        return (score(profile, normalized),
                len(profile.signature & present))

    best = NATIVE
    best_rank = rank(NATIVE)
    for profile in PROFILES:
        if profile is NATIVE:
            continue
        if score(profile, normalized) < MIN_SIGNATURE_MATCH:
            continue
        value = rank(profile)
        # Strictly greater: a tie keeps the earlier profile, and never
        # displaces the native layout.
        if value > best_rank:
            best, best_rank = profile, value
    return best


def describe(profile: Profile, headers) -> str:
    """One line for the import dialog: what was detected, and how sure."""
    pct = int(round(score(profile, normalize_headers(headers)) * 100))
    return f"{profile.label} ({pct}% column match)"


def unmapped_headers(profile: Profile, headers) -> list[str]:
    """Headers the profile has no mapping for at all.

    Reported so an import never quietly discards a column the user can see
    in their file.
    """
    known = profile.known_headers()
    return [h for h in normalize_headers(headers)
            if h and h not in known]
