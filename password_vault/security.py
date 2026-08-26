"""
Password strength, age helpers, duplicate detection, breach check, and score.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import secrets
import string
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import APP_VERSION
from .settings import PASSWORD_AGE_WARNING
from .theme import RED, ORANGE, GREEN, TEXT_QUAT, TEXT_TERT

log = logging.getLogger("PasswordVault")


# ─── Link Safety ─────────────────────────────────────────────
SAFE_URL_SCHEMES = ("http", "https")

_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):(.*)$", re.DOTALL)
_HOST_PORT_RE = re.compile(r"^\d+(?:[/?#].*)?$", re.DOTALL)


def safe_url(url: str) -> str | None:
    """Return a browser-safe absolute URL for *url*, or ``None`` to refuse.

    Entries can come from an untrusted import, and on Windows handing an
    arbitrary scheme to the shell launches whichever protocol handler is
    registered for it (``file:``, ``ms-msdt:``, ``javascript:`` …). Only
    http and https pass; a value with no scheme is treated as a bare host.
    """
    url = (url or "").strip()
    if not url or any(c in url for c in "\r\n\t"):
        return None
    if url.startswith(("/", "\\")):
        return None
    match = _SCHEME_RE.match(url)
    if match:
        scheme, rest = match.group(1).lower(), match.group(2)
        if scheme in SAFE_URL_SCHEMES:
            return url if urllib.parse.urlsplit(url).netloc else None
        # "host:8080/path" also parses as a scheme, so a port is the only
        # remainder accepted from anything that is not http(s).
        if not _HOST_PORT_RE.match(rest):
            return None
    return "https://" + url


# ─── Password Strength ───────────────────────────────────────
def password_strength(pw: str) -> tuple[int, str, str]:
    """Return ``(score 0-4, label, hex_color)`` for *pw*.

    Scoring (entropy-ish, monotonic in length and character classes):
      length: 0/1/2/3 for <8 / 8-11 / 12-15 / 16+
      classes: +1 if at least 3 of {upper, lower, digit, symbol} are present
      bonus:  +1 if all 4 classes are present AND length >= 12
    Final score is capped to 4.
    """
    if not pw:
        return 0, "", TEXT_QUAT

    if len(pw) >= 16:
        length_pts = 3
    elif len(pw) >= 12:
        length_pts = 2
    elif len(pw) >= 8:
        length_pts = 1
    else:
        length_pts = 0

    classes = sum([
        any(c.isupper() for c in pw),
        any(c.islower() for c in pw),
        any(c.isdigit() for c in pw),
        any(c in string.punctuation for c in pw),
    ])

    score = length_pts
    if classes >= 3:
        score += 1
    if classes == 4 and len(pw) >= 12:
        score += 1
    score = min(score, 4)

    labels = {0: "Very Weak", 1: "Weak", 2: "Fair",
              3: "Strong", 4: "Very Strong"}
    colors = {0: RED, 1: RED, 2: ORANGE, 3: GREEN, 4: GREEN}
    return score, labels[score], colors[score]


# ─── Password Age ────────────────────────────────────────────
def password_age_text(ts: str | None) -> tuple[str, str]:
    """Return ``(text, hex_color)`` for the password age from an ISO timestamp."""
    if not ts:
        return "", TEXT_TERT
    try:
        dt = datetime.datetime.fromisoformat(ts)
        days = (datetime.datetime.now() - dt).days
        if days < 0:
            # A timestamp in the future is corrupt or came from a machine
            # with a wrong clock; reporting "Today" hid the problem.
            return "Future?", ORANGE
        if days == 0:
            return "Today", GREEN
        if days == 1:
            return "1d", GREEN
        elif days < 7:
            return f"{days}d", GREEN
        elif days < 30:
            return f"{days // 7}w", GREEN
        elif days < 90:
            return f"{days // 30}mo", GREEN
        elif days < 180:
            return f"{days // 30}mo", ORANGE
        elif days < 365:
            return f"{days // 30}mo", RED
        else:
            return f"{days // 365}y", RED
    except (ValueError, TypeError, OverflowError):
        return "", TEXT_TERT


# ─── Duplicate Detection ─────────────────────────────────────
# One definition per question, used from every call site:
#   "is this secret reused?"      -> password_hash / group_by_password
#   "is this row already here?"   -> entry_identity / find_matching_entry


def password_hash(password: str) -> str:
    """Hash a password for grouping. Never stored, never logged."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def group_by_password(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by password hash, skipping entries without one."""
    groups: dict[str, list[dict]] = {}
    for e in entries:
        pw = e.get("password", "")
        if pw:
            groups.setdefault(password_hash(pw), []).append(e)
    return groups


def find_duplicate_passwords(entries: list[dict]) -> dict[str, list[dict]]:
    """Return hash → entries for every password used more than once."""
    return {h: g for h, g in group_by_password(entries).items() if len(g) > 1}


def is_password_reused(entries: list[dict], password: str,
                       exclude_id: str | None = None) -> bool:
    """True when *password* is already used by another entry."""
    if not password:
        return False
    target = password_hash(password)
    for e in entries:
        if exclude_id and e.get("id") == exclude_id:
            continue
        pw = e.get("password", "")
        if pw and password_hash(pw) == target:
            return True
    return False


def entry_identity(entry: dict) -> tuple[str, str]:
    """Identity used to decide whether a row is already in the vault.

    Title plus username, case-folded and trimmed: an import matches on what
    the account *is*, not on the secret, so a rotated password still counts
    as the same account.
    """
    return (entry.get("title", "").strip().casefold(),
            entry.get("username", "").strip().casefold())


def find_new_entries(existing: list[dict],
                     candidates: list[dict]) -> list[dict]:
    """Return the candidates whose identity is not present in *existing*."""
    known = {entry_identity(e) for e in existing}
    fresh = []
    for candidate in candidates:
        identity = entry_identity(candidate)
        if identity in known:
            continue
        known.add(identity)
        fresh.append(candidate)
    return fresh


# ─── Breach Check (Have I Been Pwned, k-anonymity) ───────────
def _fetch_hibp_range(prefix: str) -> dict[str, int]:
    """Fetch one k-anonymity range and parse it into ``suffix → count``.

    Only the first 5 hash characters leave the machine. Padding is requested
    so response size does not reveal how many hashes share the prefix.
    """
    req = urllib.request.Request(
        f"https://api.pwnedpasswords.com/range/{prefix}",
        headers={"User-Agent": f"PasswordVault/{APP_VERSION}",
                 "Add-Padding": "true"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    suffixes: dict[str, int] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        h, count = line.split(":", 1)
        try:
            suffixes[h] = int(count)
        except ValueError:
            continue
    return suffixes


def check_hibp_batch(
    entries: list[dict],
    progress_cb,
    done_cb,
) -> None:
    """Check passwords against HIBP in a background thread.

    Entries are grouped by password and responses are cached per hash
    prefix, so a vault with many reused passwords costs one request per
    distinct secret rather than one per entry.

    Args:
        entries: List of entry dicts with 'password' and 'id' keys.
        progress_cb: Optional callback ``(current, total)`` where *total* is
                     the entry count, invoked as entries are resolved.
        done_cb: ``(results_dict)`` called when finished.
                 *results_dict*: entry_id → breach_count
                 (0 = safe, >0 = breached, −1 = error).
    """
    results: dict[str, int] = {}

    def _worker() -> None:
        total = len(entries)
        by_password: dict[str, list[str]] = {}
        for entry in entries:
            eid = entry.get("id", "")
            pw = entry.get("password", "")
            if not pw:
                results[eid] = 0
                continue
            by_password.setdefault(pw, []).append(eid)

        checked = len(results)
        if progress_cb and checked:
            progress_cb(checked, total)

        prefix_cache: dict[str, dict[str, int]] = {}
        for pw, ids in by_password.items():
            sha1 = hashlib.sha1(pw.encode("utf-8")).hexdigest().upper()
            prefix, suffix = sha1[:5], sha1[5:]
            try:
                suffixes = prefix_cache.get(prefix)
                if suffixes is None:
                    suffixes = _fetch_hibp_range(prefix)
                    prefix_cache[prefix] = suffixes
                found = suffixes.get(suffix, 0)
            except (OSError, urllib.error.URLError, ValueError) as exc:
                log.warning("HIBP check failed for prefix %s: %s", prefix,
                            exc, exc_info=True)
                found = -1
            for eid in ids:
                results[eid] = found
            checked += len(ids)
            if progress_cb:
                progress_cb(checked, total)
        done_cb(results)

    threading.Thread(target=_worker, daemon=True).start()


# ─── Security Score Calculator ────────────────────────────────
def calculate_security_score(entries: list[dict]) -> tuple[int, dict]:
    """Return ``(score 0-100, stats_dict)``."""
    if not entries:
        return 100, {"total": 0, "strong": 0, "fair": 0, "weak": 0,
                      "duplicates": 0, "old": 0}
    total = len(entries)
    weak = fair = strong = old = 0
    now = datetime.datetime.now()

    for e in entries:
        s, _, _ = password_strength(e.get("password", ""))
        if s <= 1:
            weak += 1
        elif s == 2:
            fair += 1
        else:
            strong += 1
        ts = e.get("modified_at") or e.get("created_at")
        if ts:
            try:
                if (now - datetime.datetime.fromisoformat(ts)).days > PASSWORD_AGE_WARNING:
                    old += 1
            except (ValueError, TypeError):
                pass

    # Extra copies, not group members: three entries sharing one password are
    # two copies too many, which is what the user has to fix.
    dup_extra = sum(len(g) - 1 for g in find_duplicate_passwords(entries).values())
    deductions = 0
    if total > 0:
        deductions += (weak / total) * 40
        deductions += (fair / total) * 15
        deductions += (dup_extra / total) * 25
        deductions += (old / total) * 20
    score = max(0, min(100, int(100 - deductions)))
    return score, {"total": total, "strong": strong, "fair": fair,
                    "weak": weak, "duplicates": dup_extra, "old": old}


# ─── Password Generator (cryptographically secure) ──────────
def generate_password(length: int = 16, upper: bool = True,
                      lower: bool = True, digits: bool = True,
                      symbols: bool = True) -> str:
    """Generate a cryptographically secure random password.

    The requested length is always honored: asking for fewer characters than
    the number of enabled classes used to return a longer password than
    requested, which silently broke fields with a hard maximum. In that case
    a random subset of the classes is guaranteed instead.
    """
    if length <= 0:
        return ""
    chars = ""
    required: list[str] = []
    if upper:
        chars += string.ascii_uppercase
        required.append(secrets.choice(string.ascii_uppercase))
    if lower:
        chars += string.ascii_lowercase
        required.append(secrets.choice(string.ascii_lowercase))
    if digits:
        chars += string.digits
        required.append(secrets.choice(string.digits))
    if symbols:
        chars += string.punctuation
        required.append(secrets.choice(string.punctuation))
    if not chars:
        chars = string.ascii_letters + string.digits
    if len(required) > length:
        required = secrets.SystemRandom().sample(required, length)
    pw = required + [secrets.choice(chars)
                     for _ in range(length - len(required))]
    for i in range(len(pw) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pw[i], pw[j] = pw[j], pw[i]
    return "".join(pw)

