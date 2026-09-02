"""Knowing which machine you actually reached.

The gap this closes: the app opens dozens of sessions with one domain
account and never checks that the machine answering is the one that
answered last time. The client does its own `known_hosts` check, but on
a first connection it prints a fingerprint and asks yes/no — and a
fingerprint you have nothing to compare against is a question with no
answer, so it gets a yes.

So the app fetches the host key itself, before launching, and compares
it with what the entry recorded. That is a check the app can genuinely
make: `ssh-keyscan` needs no credentials and no session.

Three outcomes, and the middle one is the point:

* **match** — connect, say nothing.
* **not recorded yet** — offer to record it. Trust on first use, but
  made explicit and written down, rather than a prompt in a terminal.
* **mismatch** — refuse. This is the case the whole feature exists for,
  and it is the one where a warning that can be clicked through is no
  use.

Fingerprints are the `SHA256:…` form OpenSSH prints, verified against
`ssh-keygen -lf` rather than assumed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
import shutil
import subprocess

log = logging.getLogger("PasswordVault")

MATCH = "match"
UNKNOWN = "unknown"
MISMATCH = "mismatch"
UNREACHABLE = "unreachable"

# ssh-keyscan against an unreachable host otherwise holds up a launch.
SCAN_TIMEOUT_SEC = 6

_FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def fingerprint(key_blob: str) -> str:
    """The ``SHA256:…`` fingerprint of a base64 public key blob.

    The same string `ssh-keygen -lf` prints and the client shows on a
    first connection, so the two can be compared by eye as well as by
    the app: SHA-256 of the raw key, base64, padding stripped.
    """
    try:
        raw = base64.b64decode(key_blob, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"not a key blob: {exc}") from exc
    if not raw:
        raise ValueError("empty key")
    digest = hashlib.sha256(raw).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def is_fingerprint(text: str) -> bool:
    """Whether *text* is shaped like one, without trusting it."""
    return bool(_FINGERPRINT.match((text or "").strip()))


def parse_keyscan(output: str) -> list[tuple[str, str]]:
    """Read `ssh-keyscan` output into ``(keytype, fingerprint)`` pairs.

    Comment lines are dropped -- keyscan writes its progress to stdout
    on some builds, and treating a comment as a key would invent a
    fingerprint for something that is not one.
    """
    found = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        keytype, blob = parts[1], parts[2]
        if not keytype.startswith(("ssh-", "ecdsa-", "sk-")):
            continue
        try:
            found.append((keytype, fingerprint(blob)))
        except ValueError:
            continue
    return found


def _keyscan_path() -> str | None:
    candidate = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH",
        "ssh-keyscan.exe")
    if os.path.isfile(candidate):
        return candidate
    return shutil.which("ssh-keyscan")


def scan(host: str, port: int = 22,
         timeout: int = SCAN_TIMEOUT_SEC) -> tuple[list, str]:
    """Fetch a host's public keys. Returns ``(pairs, problem)``.

    No credentials are used or needed: this is the key the server offers
    to anyone who asks, which is exactly what makes it checkable before
    a session is opened.
    """
    tool = _keyscan_path()
    if not tool:
        return [], "ssh-keyscan is not installed"
    try:
        result = subprocess.run(
            [tool, "-T", str(timeout), "-p", str(int(port)), host],
            capture_output=True, text=True, timeout=timeout + 4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return [], f"{host} did not answer within {timeout}s"
    except OSError as exc:
        return [], f"could not run ssh-keyscan: {exc}"

    found = parse_keyscan(result.stdout)
    if not found:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "no key offered"
        return [], f"{host}: {reason[:120]}"
    return found, ""


def compare(expected: str, offered: list) -> str:
    """MATCH, UNKNOWN or MISMATCH, given what the entry recorded.

    A server offers several keys of different types, and a client picks
    one by preference. Recording one and matching *any* offered key is
    right: the alternative flags a host that added an ed25519 key beside
    its RSA one as an attack.
    """
    expected = (expected or "").strip()
    if not expected:
        return UNKNOWN
    if not offered:
        return UNREACHABLE
    return MATCH if any(fp == expected for _kind, fp in offered) else MISMATCH


def preferred(offered: list) -> str:
    """The fingerprint to record, when several are on offer.

    Ed25519 first: it is what a current OpenSSH negotiates by default,
    so it is the one the user will see quoted back at them.
    """
    order = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa")
    for wanted in order:
        for kind, fp in offered:
            if kind == wanted:
                return fp
    return offered[0][1] if offered else ""


# ─── What the machine already trusts ─────────────────────────
def known_hosts_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")


def in_known_hosts(host: str, port: int = 22, path: str = "") -> list:
    """Fingerprints `known_hosts` already holds for *host*.

    Read rather than written. This app does not manage that file: it
    belongs to the SSH client, hashed entries are common, and editing it
    from here would be tampering with the client's own record of trust.
    Used only to say "you have connected here before" when an entry has
    nothing recorded.
    """
    path = path or known_hosts_path()
    target = host.strip().lower()
    needle = f"[{target}]:{port}" if port != 22 else target
    found = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                hosts, keytype, blob = parts[0], parts[1], parts[2]
                names = [h.strip().lower() for h in hosts.split(",")]
                # A hashed entry (|1|…) cannot be matched by name without
                # the salt, and guessing would produce false confidence.
                if any(n.startswith("|") for n in names):
                    continue
                if needle not in names and target not in names:
                    continue
                try:
                    found.append((keytype, fingerprint(blob)))
                except ValueError:
                    continue
    except OSError:
        return []
    return found
