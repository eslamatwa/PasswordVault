"""Handing Remote Desktop a credential, and taking it back.

`mstsc` takes no password on its command line, deliberately. What it does
do is look in the Windows Credential Manager for `TERMSRV/<host>` and use
whatever it finds, which is how "connect without being asked" works for
saved connections.

So the app writes the credential, launches, and deletes it again. Three
things make that a reasonable trade rather than a hack:

* It goes in through `CredWriteW`, not `cmdkey`. `cmdkey /pass:` puts the
  password in a **command line**, which every other process on the
  machine can read out of the process list for as long as it runs.
* It is written as session-scoped, so a crash or a power cut cannot
  leave it behind past logoff.
* It is deleted a short time after the client starts, and the deletion
  is verified rather than assumed.

The user is still told it happens. A password manager quietly putting
secrets into another store is exactly the kind of thing that should not
be a surprise.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger("PasswordVault")

IS_WINDOWS = sys.platform == "win32"

CRED_TYPE_DOMAIN_PASSWORD = 2
# Session persistence: the credential does not survive a logoff even if
# something goes wrong before it is deleted.
CRED_PERSIST_SESSION = 1

# How long the credential stays after the client is launched. mstsc reads
# it while connecting; leaving it longer is leaving a password in another
# process's store for no reason.
CREDENTIAL_SECONDS = 30

if IS_WINDOWS:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32.CredWriteW.argtypes = (ctypes.POINTER(CREDENTIALW),
                                    wintypes.DWORD)
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                     wintypes.DWORD)
    advapi32.CredDeleteW.restype = wintypes.BOOL
    advapi32.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p)
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = (ctypes.c_void_p,)


def target_for(host: str) -> str:
    """The name Remote Desktop looks under."""
    return f"TERMSRV/{(host or '').strip()}"


def available() -> bool:
    return IS_WINDOWS


# Windows refuses some usernames outright, and the error it returns
# (2202, ERROR_BAD_USERNAME) is a number rather than an explanation. The
# two that come up in practice:
#
#   .\name   -- the "this machine" prefix is not accepted for a domain
#               credential, though it is fine at a login prompt
#   a tab or newline inside the name, which is almost always a copy and
#   paste accident and is invisible in a text field
ERROR_BAD_USERNAME = 2202


def check_username(username: str) -> str:
    """Why Windows will refuse this username, or ''."""
    if not username:
        # Without one mstsc asks anyway, and a credential with an empty
        # user is a stray entry that helps nobody.
        return "no username, so Remote Desktop would ask regardless"
    if any(ch in username for ch in "\t\r\n"):
        return ("the username contains a tab or a line break -- usually "
                "a stray character from a copy and paste")
    if username.startswith(".\\"):
        return ("Windows will not store a credential for a '.\\name' "
                "username. Use the plain name, or DOMAIN\\name.")
    return ""


def write(host: str, username: str, password: str) -> str:
    """Store a credential for *host*. Returns a problem, or ''."""
    if not IS_WINDOWS:
        return "only available on Windows"
    if not host:
        return "no host"
    problem = check_username(username)
    if problem:
        return problem

    blob = (password or "").encode("utf-16-le")
    buffer = (ctypes.c_byte * len(blob)).from_buffer_copy(blob)

    cred = CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_DOMAIN_PASSWORD
    cred.TargetName = target_for(host)
    cred.Comment = "Written by Password Vault; removed after connecting."
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(
        buffer, ctypes.POINTER(ctypes.c_byte)) if blob else None
    cred.Persist = CRED_PERSIST_SESSION
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = username

    if not advapi32.CredWriteW(ctypes.byref(cred), 0):
        code = ctypes.get_last_error()
        if code == ERROR_BAD_USERNAME:
            return (f"Windows will not accept {username!r} as a username "
                    "for a stored credential")
        return f"Windows refused to store the credential (error {code})"
    return ""


def exists(host: str) -> bool:
    """Whether a credential for *host* is currently stored."""
    if not IS_WINDOWS:
        return False
    pointer = ctypes.c_void_p()
    ok = advapi32.CredReadW(target_for(host), CRED_TYPE_DOMAIN_PASSWORD,
                            0, ctypes.byref(pointer))
    if ok and pointer:
        advapi32.CredFree(pointer)
    return bool(ok)


def delete(host: str) -> bool:
    """Remove the credential. True when it is gone afterwards.

    Checked rather than assumed: leaving a password in another process's
    store because a delete quietly failed is the failure that matters
    here, and it is silent.
    """
    if not IS_WINDOWS:
        return True
    advapi32.CredDeleteW(target_for(host), CRED_TYPE_DOMAIN_PASSWORD, 0)
    still_there = exists(host)
    if still_there:
        log.warning("An RDP credential for %s could not be removed.", host)
    return not still_there
