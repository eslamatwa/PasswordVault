"""
Password strength, age helpers, duplicate detection, breach check, and score.
"""

from __future__ import annotations

import datetime
import hashlib
import http.client
import logging
import secrets
import string
import threading
import time

from . import APP_VERSION
from .settings import PASSWORD_AGE_WARNING
from .theme import RED, ORANGE, GREEN, TEXT_QUAT, TEXT_TERT

log = logging.getLogger("PasswordVault")


# ─── Password Strength ───────────────────────────────────────
def password_strength(pw: str) -> tuple[int, str, str]:
    """Return ``(score 0-4, label, hex_color)`` for *pw*."""
    if not pw:
        return 0, "", TEXT_QUAT
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    if any(c.isupper() for c in pw) and any(c.islower() for c in pw):
        score += 1
    if any(c.isdigit() for c in pw):
        score += 0.5
    if any(c in string.punctuation for c in pw):
        score += 0.5
    score = min(int(score), 4)
    labels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Strong", 4: "Very Strong"}
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
        if days <= 0:
            return "Today", GREEN
        elif days == 1:
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
def find_duplicate_passwords(entries: list[dict]) -> dict[str, list[dict]]:
    """Return dict of hash → list-of-entries for passwords used >1 time."""
    pw_map: dict[str, list[dict]] = {}
    for e in entries:
        pw = e.get("password", "")
        if pw:
            h = hashlib.sha256(pw.encode()).hexdigest()
            pw_map.setdefault(h, []).append(e)
    return {k: v for k, v in pw_map.items() if len(v) > 1}


# ─── Breach Check (Have I Been Pwned, k-anonymity) ───────────
def check_hibp_batch(
    entries: list[dict],
    progress_cb,
    done_cb,
) -> None:
    """Check passwords against HIBP in a background thread.

    Args:
        entries: List of entry dicts with 'password' and 'id' keys.
        progress_cb: Optional callback ``(current, total)`` invoked after
                     each entry is checked.
        done_cb: ``(results_dict)`` called when finished.
                 *results_dict*: entry_id → breach_count
                 (0 = safe, >0 = breached, −1 = error).
    """
    results: dict[str, int] = {}

    def _worker() -> None:
        total = len(entries)
        # Reuse a single HTTPS connection for all requests
        conn: http.client.HTTPSConnection | None = None
        try:
            conn = http.client.HTTPSConnection(
                "api.pwnedpasswords.com", timeout=10)
            conn._http_vsn = 10
            conn._http_vsn_str = "HTTP/1.0"
        except (OSError, http.client.HTTPException):
            conn = None

        for idx, entry in enumerate(entries):
            pw = entry.get("password", "")
            eid = entry.get("id", "")
            if not pw:
                results[eid] = 0
                if progress_cb:
                    progress_cb(idx + 1, total)
                continue
            try:
                sha1 = hashlib.sha1(pw.encode("utf-8")).hexdigest().upper()
                prefix, suffix = sha1[:5], sha1[5:]
                # Reconnect if previous connection was lost
                if conn is None:
                    conn = http.client.HTTPSConnection(
                        "api.pwnedpasswords.com", timeout=10)
                    conn._http_vsn = 10
                    conn._http_vsn_str = "HTTP/1.0"
                conn.request("GET", f"/range/{prefix}",
                             headers={"User-Agent": f"PasswordVault/{APP_VERSION}"})
                resp = conn.getresponse()
                found = 0
                if resp.status == 200:
                    body = resp.read().decode("utf-8")
                    for line in body.splitlines():
                        h, count = line.strip().split(":")
                        if h == suffix:
                            found = int(count)
                            break
                else:
                    resp.read()
                    found = -1
                results[eid] = found
            except (OSError, http.client.HTTPException, ValueError) as exc:
                log.warning("HIBP check failed for entry %s: %s", eid,
                            exc, exc_info=True)
                results[eid] = -1
                # Connection may be broken, reset it
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
                conn = None
            if progress_cb:
                progress_cb(idx + 1, total)
            time.sleep(0.2)

        # Clean up
        try:
            if conn:
                conn.close()
        except Exception:
            pass
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
    pw_set: dict[str, list] = {}
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
        pw = e.get("password", "")
        if pw:
            h = hashlib.sha256(pw.encode()).hexdigest()
            pw_set.setdefault(h, []).append(e)

    dup_entries = sum(len(v) for v in pw_set.values() if len(v) > 1)
    deductions = 0
    if total > 0:
        deductions += (weak / total) * 40
        deductions += (fair / total) * 15
        deductions += (dup_entries / total) * 25
        deductions += (old / total) * 20
    score = max(0, min(100, int(100 - deductions)))
    return score, {"total": total, "strong": strong, "fair": fair,
                    "weak": weak, "duplicates": dup_entries, "old": old}


# ─── Password Generator (cryptographically secure) ──────────
def generate_password(length: int = 16, upper: bool = True,
                      lower: bool = True, digits: bool = True,
                      symbols: bool = True) -> str:
    """Generate a cryptographically secure random password."""
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
    pw = required + [secrets.choice(chars) for _ in range(max(length - len(required), 0))]
    for i in range(len(pw) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pw[i], pw[j] = pw[j], pw[i]
    return "".join(pw)

