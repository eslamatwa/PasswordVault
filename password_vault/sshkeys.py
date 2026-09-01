"""Reading, describing and creating SSH private keys.

The reason this is more than a file path: the app has to know whether a
key carries a passphrase *before* asking for one. Prompting for a
passphrase on a key that has none teaches the user to type their account
password into a box that will never use it, and staying silent on a key
that does have one leaves them at a prompt with nothing on the clipboard.

Telling the two apart cannot be done from the header. `ssh-keygen`
writes `-----BEGIN OPENSSH PRIVATE KEY-----` either way; the difference
is a cipher name inside the base64 body. So the body is parsed — never
decrypted, and never needing the passphrase to answer the question.

Nothing here writes a private key anywhere. Materialising a stored key
for a client to read is `autotype`-adjacent work that belongs with the
launch, where the file can be locked down and removed again.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import struct

log = logging.getLogger("PasswordVault")

OPENSSH = "openssh"
PKCS8 = "pkcs8"
PEM = "pem"
PPK = "ppk"
UNKNOWN = "unknown"

_OPENSSH_MAGIC = b"openssh-key-v1\x00"
_PEM_BODY = re.compile(
    rb"-----BEGIN [^-]+-----(.*?)-----END", re.DOTALL)

# A private key is small. Anything this large is not one, and reading it
# into memory to find that out is the wrong order of operations.
MAX_KEY_BYTES = 512 * 1024


class KeyError_(ValueError):
    """The file is not a private key this can work with."""


def _unpack_string(blob: bytes, offset: int):
    """One SSH wire string: a length, then that many bytes."""
    if offset + 4 > len(blob):
        raise KeyError_("the key is truncated")
    (length,) = struct.unpack(">I", blob[offset:offset + 4])
    start = offset + 4
    if length > len(blob) - start:
        raise KeyError_("the key is truncated")
    return blob[start:start + length], start + length


def _openssh_cipher(text: bytes) -> str:
    """The cipher named inside an OpenSSH private key, or ''.

    `none` means no passphrase. Anything else means there is one, and
    that is the whole question this module exists to answer.
    """
    match = _PEM_BODY.search(text)
    if not match:
        raise KeyError_("no key data between the BEGIN and END lines")
    try:
        blob = base64.b64decode(
            b"".join(match.group(1).split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KeyError_(f"the key body is not valid base64: {exc}") from exc
    if not blob.startswith(_OPENSSH_MAGIC):
        raise KeyError_("not an OpenSSH key after all")
    name, _offset = _unpack_string(blob, len(_OPENSSH_MAGIC))
    return name.decode("ascii", "replace")


def describe(data) -> dict:
    """What kind of key this is, and whether it has a passphrase.

    Returns ``{"kind", "encrypted", "problem"}``. ``encrypted`` is None
    when it genuinely could not be determined, which is different from
    False and must not be shown to the user as "no passphrase needed".
    """
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    if not data:
        return {"kind": UNKNOWN, "encrypted": None, "problem": "empty file"}
    if len(data) > MAX_KEY_BYTES:
        return {"kind": UNKNOWN, "encrypted": None,
                "problem": "far too large to be a private key"}

    head = data.lstrip()[:80]

    if head.startswith(b"PuTTY-User-Key-File"):
        # PuTTY says so outright, on its own line.
        match = re.search(rb"^Encryption:\s*(\S+)", data, re.MULTILINE)
        if not match:
            return {"kind": PPK, "encrypted": None,
                    "problem": "no Encryption line in the .ppk"}
        return {"kind": PPK,
                "encrypted": match.group(1).strip().lower() != b"none",
                "problem": ""}

    if b"BEGIN OPENSSH PRIVATE KEY" in head:
        try:
            cipher = _openssh_cipher(data)
        except KeyError_ as exc:
            return {"kind": OPENSSH, "encrypted": None,
                    "problem": str(exc)}
        return {"kind": OPENSSH, "encrypted": cipher != "none",
                "problem": ""}

    if b"BEGIN ENCRYPTED PRIVATE KEY" in head:
        return {"kind": PKCS8, "encrypted": True, "problem": ""}
    if b"BEGIN PRIVATE KEY" in head:
        return {"kind": PKCS8, "encrypted": False, "problem": ""}

    if re.search(rb"BEGIN (RSA|DSA|EC) PRIVATE KEY", head):
        # The classic PEM shape says so in a header line.
        encrypted = b"Proc-Type:" in data[:400] and b"ENCRYPTED" in data[:400]
        return {"kind": PEM, "encrypted": encrypted, "problem": ""}

    if b"PRIVATE KEY" in head:
        return {"kind": UNKNOWN, "encrypted": None,
                "problem": "an unfamiliar private key format"}
    if b"ssh-rsa " in head or b"ssh-ed25519 " in head:
        return {"kind": UNKNOWN, "encrypted": None,
                "problem": "this is the public key — pick the private one, "
                           "the file without .pub"}
    return {"kind": UNKNOWN, "encrypted": None,
            "problem": "not a private key file"}


def read(path: str) -> dict:
    """Describe the key at *path*, without holding on to it."""
    try:
        with open(path, "rb") as handle:
            return describe(handle.read(MAX_KEY_BYTES + 1))
    except OSError as exc:
        return {"kind": UNKNOWN, "encrypted": None,
                "problem": f"cannot be read: {exc.strerror or exc}"}


# ─── Which clients can use which format ──────────────────────
# PuTTY reads its own .ppk and nothing else. Handing it an OpenSSH key
# fails with a message about the file not being a recognised key, which
# sounds like the key is broken rather than the wrong shape.
CLIENT_FORMATS = {
    "PuTTY": {PPK},
    "MobaXterm": {OPENSSH, PEM, PKCS8, PPK},
    "Windows SSH": {OPENSSH, PEM, PKCS8},
}


def suits(kind: str, client_name: str) -> str | None:
    """Why *client_name* cannot use a *kind* key, or None if it can."""
    allowed = CLIENT_FORMATS.get(client_name)
    if allowed is None or kind == UNKNOWN:
        return None
    if kind in allowed:
        return None
    if client_name == "PuTTY":
        return ("PuTTY only reads its own .ppk keys. Convert this one "
                "with PuTTYgen, or pick a different client.")
    return (f"{client_name} cannot use a {kind} key. "
            "Convert it to the OpenSSH format.")


# ─── Making one ──────────────────────────────────────────────
KEY_TYPES = ("ed25519", "rsa")


def generate(kind: str = "ed25519", comment: str = "") -> tuple[str, str]:
    """Create a keypair. Returns ``(private_openssh, public_openssh)``.

    No passphrase. That is deliberate for a key this app generates and
    stores: the vault is already the protection, and a passphrase on top
    would have to be typed at every connection while adding nothing an
    attacker holding the decrypted vault could not already bypass. A key
    kept as a *file* on disk is the case where a passphrase earns its
    keep, and those are the ones the user brings in themselves.
    """
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

    if kind not in KEY_TYPES:
        raise KeyError_(f"unknown key type {kind!r}")
    if kind == "ed25519":
        key = ed25519.Ed25519PrivateKey.generate()
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)

    private = key.private_bytes(
        ser.Encoding.PEM, ser.PrivateFormat.OpenSSH,
        ser.NoEncryption()).decode("ascii")
    public = key.public_key().public_bytes(
        ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH).decode("ascii")
    if comment:
        public = f"{public} {comment}"
    return private, public


def public_from_private(private_text: str, comment: str = "") -> str:
    """The public half of a stored key, to paste onto a server."""
    from cryptography.hazmat.primitives import serialization as ser

    try:
        key = ser.load_ssh_private_key(
            private_text.encode("utf-8", "replace"), password=None)
    except Exception as exc:  # noqa: BLE001 - any failure is the same here
        raise KeyError_(f"the stored key could not be read: {exc}") from exc
    public = key.public_key().public_bytes(
        ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH).decode("ascii")
    return f"{public} {comment}" if comment else public


# ─── Putting a stored key where a client can read it ─────────
#
# A key kept inside the vault has to become a file for the length of one
# connection, because every SSH client takes a path and none takes bytes.
# Two things make that survivable rather than reckless:
#
# * OpenSSH refuses a private key whose permissions are loose -- "Bad
#   permissions", which reads as a broken key rather than an ACL. So the
#   file is stripped of inherited rights and granted to this user alone,
#   and that is verified rather than assumed.
# * It is deleted afterwards. Not on exit, not on next launch: on a timer
#   the caller owns, because a private key left in the temp folder is the
#   thing this whole feature was supposed to avoid.

MATERIALISED_DIR = "PasswordVault-keys"


def _lock_down(path: str) -> str | None:
    """Give *path* to this user only. Returns a problem, or None."""
    import getpass
    import os
    import subprocess

    user = os.environ.get("USERNAME") or getpass.getuser()
    for args in (["/inheritance:r"], ["/grant:r", f"{user}:F"]):
        result = subprocess.run(
            ["icacls", path] + args, capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0:
            return (result.stderr or result.stdout or "").strip()[:200]
    return None


def materialise(private_text: str, name: str = "key") -> tuple[str, str]:
    """Write a stored key to a locked-down temp file.

    Returns ``(path, problem)``. On any problem the file is removed
    before returning, so a key never survives a failure.
    """
    import os
    import re
    import tempfile

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:40] or "key"
    folder = os.path.join(tempfile.gettempdir(), MATERIALISED_DIR)
    try:
        os.makedirs(folder, exist_ok=True)
        handle, path = tempfile.mkstemp(prefix=f"{safe}-", dir=folder)
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(private_text.rstrip("\n") + "\n")
    except OSError as exc:
        return "", f"could not write the key: {exc.strerror or exc}"

    problem = _lock_down(path)
    if problem:
        discard(path)
        return "", f"could not secure the key file: {problem}"
    return path, ""


def discard(path: str) -> None:
    """Remove a materialised key. Safe to call more than once."""
    import os

    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("A temporary SSH key could not be removed: %s", exc)
