"""Reading a hotkey the user typed, and saying why one cannot be used.

`RegisterHotKey` is deliberate: it hands the app the one combination it
asked for and nothing else. The alternative, a low-level keyboard hook,
would see every keystroke on the machine — which is what a keylogger is,
is what antivirus software treats it as, and is not a thing a password
manager should be doing to read one shortcut.

Parsing lives here, apart from the registration, because the failures
worth getting right are all about what the user typed: a combination
Windows will not accept, one with no modifier, or one another program
already owns.
"""

from __future__ import annotations

# RegisterHotKey modifier bits.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Without this, holding the combination repeats it as fast as the key
# repeats -- which for auto-type means typing the password again and
# again into the same field.
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "cmd": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "backslash": 0xDC, "semicolon": 0xBA, "comma": 0xBC,
    "period": 0xBE, "slash": 0xBF, "backtick": 0xC0,
}

# Combinations Windows itself owns. Registering these either fails or,
# worse, takes them away from the shell for the life of the process.
_RESERVED = {
    (MOD_CONTROL | MOD_ALT, 0x2E),           # Ctrl+Alt+Del
    (MOD_WIN, ord("L")),                     # Win+L, lock
    (MOD_CONTROL | MOD_SHIFT, 0x1B),         # Ctrl+Shift+Esc
}

DEFAULT_FULL = "Ctrl+Alt+V"
DEFAULT_USERNAME = "Ctrl+Alt+U"
DEFAULT_PASSWORD = "Ctrl+Alt+P"


class HotkeyError(ValueError):
    """The combination cannot be registered as written."""


def parse(text: str) -> tuple[int, int]:
    """Read ``"Ctrl+Alt+V"`` into ``(modifiers, virtual key)``.

    A modifier is required. A bare key would take that key away from
    every other program on the machine for as long as the vault is
    running, which is not something to allow by typo.
    """
    raw = (text or "").strip()
    if not raw:
        raise HotkeyError("no shortcut set")

    parts = [p.strip().lower() for p in raw.split("+") if p.strip()]
    if not parts:
        raise HotkeyError("no shortcut set")

    modifiers, key = 0, None
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
            continue
        if key is not None:
            raise HotkeyError(
                f"'{raw}' names more than one key; use modifiers plus one key")
        key = part

    if key is None:
        raise HotkeyError(f"'{raw}' is only modifiers — add a key")
    if not modifiers:
        raise HotkeyError(
            f"'{raw}' needs a modifier: Ctrl, Alt, Shift or Win. Without "
            "one it would take that key from every other program.")

    code = _virtual_key(key)
    if code is None:
        raise HotkeyError(f"'{key}' is not a key this can register")
    if (modifiers & ~MOD_NOREPEAT, code) in _RESERVED:
        raise HotkeyError(f"'{raw}' is reserved by Windows")
    return modifiers | MOD_NOREPEAT, code


def _virtual_key(name: str):
    if len(name) == 1:
        if name.isalpha():
            return ord(name.upper())
        if name.isdigit():
            return ord(name)
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name]
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return None


def normalise(text: str) -> str:
    """The canonical spelling of a shortcut, for storing and showing."""
    modifiers, code = parse(text)
    order = [(MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"),
             (MOD_SHIFT, "Shift"), (MOD_WIN, "Win")]
    names = [label for bit, label in order if modifiers & bit]
    return "+".join(names + [_key_name(code)])


def _key_name(code: int) -> str:
    for name, value in _NAMED_KEYS.items():
        if value == code:
            return name.capitalize()
    if 0x70 <= code <= 0x87:
        return f"F{code - 0x70 + 1}"
    return chr(code).upper()


# What Tk reports in `event.state` on Windows, measured rather than
# assumed: every event also carries baseline bits (0x8 and 0x20 here) for
# keyboard state that has nothing to do with the shortcut, so only these
# are read and the rest ignored.
TK_SHIFT = 0x0001
TK_CONTROL = 0x0004
TK_ALT = 0x20000

# Pressing one of these is not a shortcut yet, it is the user on their
# way to one.
_MODIFIER_KEYS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3,
                  0xA4, 0xA5}


def is_modifier_key(keycode: int) -> bool:
    return keycode in _MODIFIER_KEYS


def from_event(state: int, keycode: int) -> str:
    """Turn a Tk key event into a shortcut string.

    Reads `event.keycode`, not `event.keysym`. On Windows the keycode is
    the virtual key, the same number `RegisterHotKey` wants, and it does
    not change with the keyboard layout. The keysym does: with an Arabic
    layout active, Ctrl+Alt+V arrives with a keysym of `??`, which is
    exactly the trap this project already hit once with its Ctrl
    shortcuts.
    """
    if is_modifier_key(keycode):
        raise HotkeyError("that is only a modifier — hold it and press a key")
    names = []
    if state & TK_CONTROL:
        names.append("Ctrl")
    if state & TK_ALT:
        names.append("Alt")
    if state & TK_SHIFT:
        names.append("Shift")
    if not names:
        raise HotkeyError(
            "hold Ctrl, Alt or Shift as well — a key on its own would be "
            "taken from every other program")
    key = _key_name(keycode)
    if key is None or not key:
        raise HotkeyError("that key cannot be used in a shortcut")
    return normalise("+".join(names + [key]))


def validate(text: str) -> str | None:
    """The problem with a shortcut, or None. For a settings field."""
    try:
        parse(text)
    except HotkeyError as exc:
        return str(exc)
    return None


def clashes(shortcuts: dict):
    """The first pair of shortcuts set to the same combination.

    Returns ``(name, other_name, combination)`` or None. The parts are
    returned rather than a sentence so the caller can put them into a
    translated one -- a message built here would arrive in English
    whatever language the app is in.

    Worth checking at all because Windows refuses the second
    registration silently: without this, one shortcut simply stops
    working and nothing says which.
    """
    seen = {}
    for name, text in shortcuts.items():
        if not (text or "").strip():
            continue
        try:
            combo = parse(text)
        except HotkeyError:
            continue
        if combo in seen:
            return name, seen[combo], normalise(text)
        seen[combo] = name
    return None
