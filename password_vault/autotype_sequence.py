"""What auto-type actually sends, and in what order.

A login form is not always username-Tab-password. Microsoft and Google
ask for the account on one page and the password on the next, so sending
both at once puts the password into a page that has already gone. Other
forms want a click, or a domain prefix, or no Enter at all.

So the order is per entry and editable, in the notation KeePass uses and
most people have already seen::

    {USERNAME}{TAB}{PASSWORD}{ENTER}

Parsing it here, apart from anything that can press a key, means the
awkward cases can be tested without a keyboard: an unknown token, an
unclosed brace, a sequence that would send a password to a window that
never asked for a username.
"""

from __future__ import annotations

import re

DEFAULT = "{USERNAME}{TAB}{PASSWORD}{ENTER}"

# Only these. An unknown token is refused rather than skipped: a
# sequence that silently drops a step types half a login and leaves the
# user guessing which half.
KEYS = {
    "TAB": "tab",
    "ENTER": "enter",
    "RETURN": "enter",
    "SPACE": "space",
    "ESC": "escape",
    "ESCAPE": "escape",
    "BACKSPACE": "backspace",
    "DELETE": "delete",
    "HOME": "home",
    "END": "end",
}
FIELDS = {"USERNAME": "username", "PASSWORD": "password",
          "URL": "url", "TITLE": "title"}

_TOKEN = re.compile(r"\{([^{}]*)\}")
# A pause, for a page that swaps its form in after the first field.
_DELAY = re.compile(r"^DELAY\s+(\d{1,5})$", re.IGNORECASE)

MAX_DELAY_MS = 10000


class SequenceError(ValueError):
    """The sequence cannot be carried out as written."""


def parse(sequence: str):
    """Turn a sequence into steps, or say why it cannot be.

    Each step is ``("text", literal)``, ``("field", name)``,
    ``("key", name)`` or ``("delay", milliseconds)``. Fields are not
    resolved here — the value of a password has no business in a parser,
    and keeping it out means these tests never hold one.
    """
    text = DEFAULT if sequence is None else str(sequence)
    if not text.strip():
        raise SequenceError("the sequence is empty")

    steps, position = [], 0
    for match in _TOKEN.finditer(text):
        if match.start() > position:
            steps.append(("text", text[position:match.start()]))
        name = match.group(1).strip().upper()
        delay = _DELAY.match(name)
        if delay:
            milliseconds = int(delay.group(1))
            if not 0 < milliseconds <= MAX_DELAY_MS:
                raise SequenceError(
                    f"a delay must be between 1 and {MAX_DELAY_MS} ms")
            steps.append(("delay", milliseconds))
        elif name in FIELDS:
            steps.append(("field", FIELDS[name]))
        elif name in KEYS:
            steps.append(("key", KEYS[name]))
        elif not name:
            raise SequenceError("empty {} in the sequence")
        else:
            raise SequenceError(f"'{{{match.group(1)}}}' is not a known step")
        position = match.end()

    if position < len(text):
        steps.append(("text", text[position:]))

    # An unclosed brace would otherwise be typed as literal text, which
    # for `{PASSWORD` means the word rather than the secret -- a failure
    # that looks like the password being wrong.
    leftovers = "".join(part for kind, part in steps
                        if kind == "text" and isinstance(part, str))
    if "{" in leftovers or "}" in leftovers:
        raise SequenceError("an unclosed { or } in the sequence")
    if not steps:
        raise SequenceError("the sequence does nothing")
    return steps


def uses(sequence, field: str) -> bool:
    """Whether a sequence sends a particular field. Never raises."""
    try:
        return any(kind == "field" and name == field
                   for kind, name in parse(sequence))
    except SequenceError:
        return False


def describe(sequence) -> str:
    """A plain reading of a sequence, for a confirmation prompt."""
    try:
        steps = parse(sequence)
    except SequenceError as exc:
        return str(exc)
    words = []
    for kind, value in steps:
        if kind == "field":
            words.append({"username": "your username",
                          "password": "your password",
                          "url": "the address",
                          "title": "the title"}[value])
        elif kind == "key":
            words.append(value.capitalize())
        elif kind == "delay":
            words.append(f"wait {value}ms")
        elif value.strip():
            words.append(f"'{value}'")
    return " → ".join(words)


def validate(sequence) -> str | None:
    """The problem with a sequence, or None. For a settings field."""
    try:
        parse(sequence)
    except SequenceError as exc:
        return str(exc)
    return None
