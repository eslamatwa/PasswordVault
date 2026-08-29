"""Turning a typed list of servers into things to connect to.

Kept apart from the dialog so the parsing can be tested without a window,
because this is where a mistake is expensive: a line read wrongly is a
session opened to the wrong machine with a domain account.
"""

from __future__ import annotations

DEFAULT_PORT = 22


def split_target(line: str) -> tuple[str, str, int | None, str | None]:
    """Split one ``[user@]host[:port]`` line.

    Returns ``(user, host, port, error)``; *port* is None when the line
    did not name one, so the caller can supply its own default rather
    than having 22 baked in here.

    A colon is only a port separator when what follows is entirely
    digits. Otherwise it is left in the host, where it will be refused
    later rather than silently cut in half.
    """
    raw = line.strip()
    if not raw:
        return "", "", None, None

    user = ""
    if "@" in raw:
        # rsplit: a username may legitimately contain @ (an email address
        # as a login), and the last @ is the one separating it from the
        # host.
        user, _, raw = raw.rpartition("@")
        user = user.strip()
        raw = raw.strip()
        if not user:
            return "", "", None, "starts with '@'"

    port = None
    if ":" in raw:
        head, _, tail = raw.rpartition(":")
        if not head:
            return user, "", None, "no host before ':'"
        if not tail.isdigit():
            # Leaving it in the host only defers the failure to ssh,
            # which reports it as the machine being unreachable.
            return user, raw, None, f"port '{tail}' is not a number"
        number = int(tail)
        if not 1 <= number <= 65535:
            return user, head, None, f"port {tail} is out of range"
        raw, port = head, number

    if not raw:
        return user, "", port, "no host"
    if ":" in raw:
        # More than one colon. An IPv6 literal would need brackets, and
        # nothing else with a colon in it is a host.
        return user, raw, port, f"'{raw}' is not a host"
    return user, raw, port, None


def parse_hosts(text, default_user="", default_port=DEFAULT_PORT,
                check=None):
    """Read a typed block of servers into targets and complaints.

    One per line. Blank lines and anything after a ``#`` are ignored, so
    a list can be pasted with notes in it. Duplicates are dropped, since
    the same machine twice means two sessions to it and no warning.

    *check* is the app's argument guard. It is passed in rather than
    imported so this module stays free of the application object, and so
    a test can see exactly which values were rejected.

    Returns ``(targets, problems)``. Both are returned: a bad line should
    not silently cost the user the twenty good ones next to it, and a
    silently dropped line is worse than a refused one.
    """
    targets, problems, seen = [], [], set()
    for number, line in enumerate(text.splitlines(), 1):
        text_part = line.split("#", 1)[0].strip()
        if not text_part:
            continue

        user, host, port, error = split_target(text_part)
        if error:
            problems.append(f"line {number}: {error}")
            continue

        user = user or default_user
        port = default_port if port is None else port

        if check is not None:
            complaint = check(host, "Host / IP") or check(user, "Username")
            if complaint:
                problems.append(f"line {number}: {complaint}")
                continue

        key = (user.lower(), host.lower(), port)
        if key in seen:
            continue
        seen.add(key)
        targets.append({"host": host, "user": user, "port": port,
                        "label": host, "problem": None})
    return targets, problems
