"""Deciding which entry a window is asking for.

Auto-type synthesises keystrokes into whatever window is in front. That
makes picking the *right* entry the whole safety story: a wrong guess
does not fail, it types a password into somewhere it does not belong.
So this is kept apart from the Windows plumbing and tested on its own.

The rule everywhere below: when in doubt, do not guess. Returning
nothing costs the user a menu; returning the wrong entry costs them a
password. A confident match needs real evidence — a hostname or an
address, not a short word that happens to appear in a title bar.

Window titles this has to cope with:

    Sign in · GitHub — Mozilla Firefox
    1. root@web01 (10.0.0.5) — MobaXterm
    10.0.0.5 — Remote Desktop Connection
    admin@fw01: ~ — Windows PowerShell
"""

from __future__ import annotations

import fnmatch
import re

# Enough evidence to type without asking. Anything below this is offered
# as a choice instead.
CONFIDENT = 60

# A host has to be at least this long before its appearance in a title
# means anything. "a.io" in a title is noise; "github.com" is not. Real
# four-character hosts exist -- t.co is one -- and they are excluded on
# purpose: refusing costs a menu, matching the wrong one costs a
# password.
MIN_HOST = 5

# Same idea for an entry's title. Two- and three-letter names match far
# too much -- "es", the entry that started all of this, would otherwise
# match "Files", "Notes" and "Settings".
MIN_TITLE_WORD = 4

_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_IPV4 = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_WORD = re.compile(r"[A-Za-z0-9]+")


def host_of(entry) -> str:
    """The hostname an entry points at, without a scheme or a path."""
    raw = (entry.get("url") or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0]
    if "@" in raw:
        raw = raw.rpartition("@")[2]
    # Strip a port, but only when it really is one.
    head, sep, tail = raw.rpartition(":")
    if sep and tail.isdigit() and head:
        raw = head
    return raw.strip().lower()


def _registrable(host: str) -> str:
    """The part of a host worth matching on.

    `login.example.com` and `www.example.com` are the same site as far as
    a person is concerned, and a title bar shows whichever it likes. An
    IP address is used whole -- every octet matters.
    """
    if not host or _IPV4.match(host):
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # Not a public-suffix list, deliberately: this decides how a title is
    # matched, not who is allowed to receive a password. Two labels is
    # right for example.com and wrong only for the co.uk shapes, where it
    # falls back to matching more strictly rather than less.
    return ".".join(parts[-2:])


def patterns_of(entry) -> list[str]:
    """The window patterns an entry claims, one per line.

    Stored as text rather than a list because it is edited as text, and
    a vault written by an older build simply has none.
    """
    raw = entry.get("match_patterns") or ""
    if isinstance(raw, (list, tuple)):
        lines = list(raw)
    else:
        lines = str(raw).splitlines()
    return [line.strip() for line in lines if line.strip()]


def pattern_matches(pattern: str, title: str) -> bool:
    """Whether *pattern* claims a window called *title*.

    A pattern with no wildcard is a plain substring, because that is what
    someone typing `intranet` means. One with a wildcard is matched with
    `fnmatch` against the whole title, wrapped so that `*.corp.local`
    still fires on "Reports — host.corp.local — Chrome".

    A pattern of nothing but wildcards is refused. It would claim every
    window on the machine, which for a feature that types passwords is
    not a power worth having by accident.
    """
    pattern = (pattern or "").strip().lower()
    title = (title or "").lower()
    if not pattern or not title:
        return False
    if not pattern.strip("*?"):
        return False
    if "*" not in pattern and "?" not in pattern:
        return pattern in title
    return (fnmatch.fnmatch(title, pattern)
            or fnmatch.fnmatch(title, f"*{pattern}*"))


# What a window title is called once the program's own name is taken
# off the end: "Outlook - Google Chrome" is about Outlook.
_APP_SUFFIX = re.compile(r"\s+[-—·|]\s+[^-—·|]+$")

# Below this a suggestion is not worth making -- it would match half the
# windows on the machine.
MIN_SUGGESTION = 4


def suggest_pattern(title: str) -> str:
    """A pattern that would make this window match next time.

    Browsers and terminals put their own name at the end of the title,
    so "Outlook - Google Chrome" becomes "Outlook" — the part that is
    about the thing the user is actually looking at.

    This exists because matching on the title alone cannot connect an
    entry called "wavz mail" at mail.wavz.com.eg to a window called
    "Outlook". Nothing in one appears in the other. Rather than pretend
    a cleverer matcher would fix that, the user is offered the one thing
    that does: remembering this window against that entry.
    """
    text = (title or "").strip()
    for _ in range(2):
        shortened = _APP_SUFFIX.sub("", text).strip()
        if shortened == text:
            break
        text = shortened
    text = text.strip(" -—·|")
    if len(text) < MIN_SUGGESTION:
        return ""
    # A title carrying its own detail — a document name, an unread count
    # — would be remembered as something that never recurs.
    return text[:60]


def is_general(entry) -> bool:
    """Whether this entry is offered for anything, on request.

    A domain account belongs to no single site. It never matches a window
    on its own -- that would mean typing it into whatever is in front --
    but it leads the list when the user asks to choose.
    """
    return bool(entry.get("general_account", False))


def score(title: str, entry) -> tuple[int, str]:
    """How well *entry* fits a window titled *title*, and why.

    Returns ``(score, reason)`` where 100 is certain and 0 is no
    evidence at all. The reason is shown to the user when the match is
    not confident enough to act on alone.
    """
    haystack = (title or "").lower()
    if not haystack:
        return 0, ""

    # A pattern the user wrote themselves outranks anything inferred:
    # they are describing windows this account is for, which is the one
    # thing the entry cannot otherwise say. It is how a domain account
    # covers `*.corp.local` without pretending to be a website.
    for pattern in patterns_of(entry):
        if pattern_matches(pattern, haystack):
            return 100, f"matches your pattern '{pattern}'"

    host = host_of(entry)
    if host and len(host) >= MIN_HOST:
        if host in haystack:
            return 100, f"{host} is in the window title"
        site = _registrable(host)
        if site != host and len(site) >= MIN_HOST and site in haystack:
            return 85, f"{site} is in the window title"
        # Browsers usually put the site's *name* in the title, not its
        # domain: "GitHub — Chrome", not "github.com — Chrome". Matching
        # the registrable domain's own label covers that, and is still
        # about the address rather than what the user called the entry.
        #
        # It has to be the registrable label, not the first one: the
        # leading label of login.example.com is "login", and matching
        # that would fire on every sign-in page on the internet.
        label = site.split(".")[0]
        if (not _IPV4.match(host) and len(label) >= MIN_TITLE_WORD
                and re.search(rf"\b{re.escape(label)}\b", haystack)):
            return 75, f"'{label}' is in the window title"

    name = (entry.get("title") or "").strip().lower()
    if name:
        words = [w for w in _WORD.findall(name) if len(w) >= MIN_TITLE_WORD]
        # The whole name, as a run of words, is much better evidence than
        # any single word of it happening to appear.
        if len(name) >= MIN_TITLE_WORD and name in haystack:
            return 70, f"'{name}' is in the window title"
        hits = [w for w in words if w in haystack]
        if hits:
            return 40, f"'{hits[0]}' is in the window title"

    user = (entry.get("username") or "").strip().lower()
    if user and len(user) >= MIN_TITLE_WORD and user in haystack:
        # On its own this is weak: a terminal shows the user it is logged
        # in as, which is the account you already used, not necessarily
        # the one being asked for.
        return 30, f"'{user}' is in the window title"

    return 0, ""


def rank(title: str, entries):
    """Every entry with any evidence, best first.

    Ties break on the longer host: between `example.com` and
    `admin.example.com` matching the same title, the more specific one
    described the window better.
    """
    scored = []
    for entry in entries or []:
        points, reason = score(title, entry)
        if points:
            scored.append((points, len(host_of(entry)), entry, reason))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [(points, entry, reason) for points, _len, entry, reason
            in scored]


def choose(title: str, entries):
    """The entry to type, or None when the user should be asked.

    None is returned both when nothing matched and when the best match is
    not clearly ahead: two entries for the same site are exactly the case
    where guessing silently types the wrong account.
    """
    ranked = rank(title, entries)
    if not ranked:
        return None
    best_points, best_entry, _reason = ranked[0]
    if best_points < CONFIDENT:
        return None
    if len(ranked) > 1 and ranked[1][0] == best_points:
        return None
    return best_entry
