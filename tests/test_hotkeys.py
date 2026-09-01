"""Reading the shortcut a user typed.

Two failures matter here, and neither is a crash. A shortcut with no
modifier takes that key away from every other program on the machine for
as long as the vault runs. Two of the app's own shortcuts set to the same
combination means Windows accepts the first and refuses the second, and
nothing says which one stopped working.

No Windows API is touched: this only decides what to ask for.
"""

from __future__ import annotations

import pytest

from password_vault.hotkeys import (
    DEFAULT_FULL, HotkeyError, MOD_ALT, MOD_CONTROL, MOD_NOREPEAT,
    MOD_SHIFT, MOD_WIN, clashes, normalise, parse, validate,
)


class TestReading:
    def test_the_default(self):
        modifiers, key = parse(DEFAULT_FULL)
        assert modifiers & MOD_CONTROL
        assert modifiers & MOD_ALT
        assert key == ord("V")

    @pytest.mark.parametrize("text", [
        "Ctrl+Alt+V", "ctrl+alt+v", "CTRL + ALT + V", " Ctrl+Alt+V ",
    ])
    def test_spelling_and_spacing_do_not_matter(self, text):
        assert parse(text) == parse(DEFAULT_FULL)

    @pytest.mark.parametrize("name,expected", [
        ("Ctrl+F5", 0x74), ("Ctrl+F12", 0x7B),
        ("Alt+Space", 0x20), ("Ctrl+Alt+Home", 0x24),
        ("Ctrl+Alt+7", ord("7")),
    ])
    def test_named_and_function_keys(self, name, expected):
        assert parse(name)[1] == expected

    def test_every_modifier(self):
        modifiers, _key = parse("Ctrl+Alt+Shift+Win+K")
        for bit in (MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN):
            assert modifiers & bit

    def test_repeat_is_always_suppressed(self):
        """Holding the combination would otherwise fire as fast as the
        key repeats — typing the password again and again."""
        assert parse(DEFAULT_FULL)[0] & MOD_NOREPEAT


class TestItRefuses:
    def test_a_key_with_no_modifier(self):
        """`V` alone would take the V key from every other program for
        as long as the vault is running."""
        with pytest.raises(HotkeyError) as caught:
            parse("V")
        assert "modifier" in str(caught.value).lower()

    def test_modifiers_with_no_key(self):
        with pytest.raises(HotkeyError):
            parse("Ctrl+Alt")

    def test_two_keys(self):
        with pytest.raises(HotkeyError):
            parse("Ctrl+V+B")

    def test_nothing_at_all(self):
        for empty in ("", "   ", None):
            with pytest.raises(HotkeyError):
                parse(empty)

    def test_a_key_windows_does_not_have(self):
        with pytest.raises(HotkeyError):
            parse("Ctrl+Alt+Frobnicate")

    def test_f25_does_not_exist(self):
        with pytest.raises(HotkeyError):
            parse("Ctrl+F25")

    @pytest.mark.parametrize("reserved", ["Win+L", "Ctrl+Alt+Delete"])
    def test_combinations_windows_owns(self, reserved):
        with pytest.raises(HotkeyError):
            parse(reserved)


class TestNormalising:
    @pytest.mark.parametrize("written,canonical", [
        ("alt+ctrl+v", "Ctrl+Alt+V"),
        ("shift+ctrl+f5", "Ctrl+Shift+F5"),
        ("ALT+SPACE", "Alt+Space"),
    ])
    def test_modifiers_come_out_in_one_order(self, written, canonical):
        """So a stored shortcut and a typed one compare equal."""
        assert normalise(written) == canonical

    def test_normalising_is_stable(self):
        once = normalise("alt+ctrl+v")
        assert normalise(once) == once


class TestValidate:
    def test_a_good_one_has_no_complaint(self):
        assert validate("Ctrl+Alt+V") is None

    def test_a_bad_one_explains_itself(self):
        message = validate("V")
        assert message and "modifier" in message.lower()


class TestClashes:
    def test_two_the_same_are_caught(self):
        """Windows takes the first and refuses the second, silently."""
        found = clashes({"Full": "Ctrl+Alt+V", "Username": "Ctrl+Alt+V"})
        assert found and "Ctrl+Alt+V" in found

    def test_the_same_written_differently_still_clashes(self):
        assert clashes({"Full": "Ctrl+Alt+V", "Username": "alt+ctrl+v"})

    def test_different_ones_are_fine(self):
        assert clashes({"Full": "Ctrl+Alt+V",
                        "Username": "Ctrl+Alt+U",
                        "Password": "Ctrl+Alt+P"}) is None

    def test_an_empty_shortcut_is_not_a_clash(self):
        """Leaving one unset is how you turn it off."""
        assert clashes({"Full": "Ctrl+Alt+V", "Username": "",
                        "Password": "   "}) is None

    def test_an_invalid_one_is_left_to_validate(self):
        """clashes() reports duplicates; it is not a second validator,
        and reporting the same problem twice helps nobody."""
        assert clashes({"Full": "Ctrl+Alt+V", "Username": "nonsense"}) is None

    def test_the_defaults_do_not_clash(self):
        from password_vault import hotkeys

        assert clashes({"full": hotkeys.DEFAULT_FULL,
                        "user": hotkeys.DEFAULT_USERNAME,
                        "pass": hotkeys.DEFAULT_PASSWORD}) is None


class TestCapturingFromTheKeyboard:
    """The settings field where you press the combination instead of
    typing its name.

    The numbers here were measured on a real machine rather than assumed
    (see the probe in the commit that added this): Ctrl+Alt+V arrives as
    keycode 0x56 with state 0x2002C, and every event also carries
    baseline bits that have nothing to do with the shortcut.
    """

    def test_the_measured_ctrl_alt_v(self):
        from password_vault.hotkeys import from_event

        assert from_event(0x2002C, 0x56) == "Ctrl+Alt+V"

    def test_the_measured_ctrl_a(self):
        from password_vault.hotkeys import from_event

        assert from_event(0x2C, 0x41) == "Ctrl+A"

    def test_baseline_bits_are_ignored(self):
        """0x8 and 0x20 are present in every event on this machine and
        mean nothing here. Reading them as modifiers would invent a Win
        or Shift that was never pressed."""
        from password_vault.hotkeys import from_event

        assert from_event(0x28 | 0x4, 0x41) == "Ctrl+A"

    def test_shift_is_read(self):
        from password_vault.hotkeys import from_event

        assert from_event(0x28 | 0x4 | 0x1, 0x41) == "Ctrl+Shift+A"

    @pytest.mark.parametrize("keycode", [0x10, 0x11, 0x12, 0x5B])
    def test_a_modifier_on_its_own_is_not_a_shortcut_yet(self, keycode):
        """Pressing Ctrl is the user on the way to a combination, not a
        combination. Accepting it would end the capture too early."""
        from password_vault.hotkeys import HotkeyError, from_event

        with pytest.raises(HotkeyError):
            from_event(0x2C, keycode)

    def test_a_bare_key_is_refused_with_a_reason(self):
        from password_vault.hotkeys import HotkeyError, from_event

        with pytest.raises(HotkeyError) as caught:
            from_event(0x28, 0x41)
        assert "every other program" in str(caught.value)

    def test_a_function_key_captures(self):
        from password_vault.hotkeys import from_event

        assert from_event(0x2C, 0x74) == "Ctrl+F5"

    def test_what_is_captured_can_be_registered(self):
        """The whole point: capture produces something parse() accepts."""
        from password_vault.hotkeys import from_event

        for state, keycode in ((0x2002C, 0x56), (0x2C, 0x41),
                               (0x2C, 0x74)):
            parse(from_event(state, keycode))
