"""The order auto-type sends things in.

The failure that matters: a sequence that goes wrong halfway types a
password somewhere that never asked for one. So a sequence is either
carried out as written or refused outright — never partly performed, and
never silently repaired.

No keyboard involved, and deliberately no passwords: the parser works in
field *names*, so nothing here has to hold a secret to test it.
"""

from __future__ import annotations

import pytest

from password_vault.autotype_sequence import (
    DEFAULT, SequenceError, describe, parse, uses, validate,
)


class TestTheDefault:
    def test_it_is_username_tab_password_enter(self):
        assert parse(DEFAULT) == [
            ("field", "username"), ("key", "tab"),
            ("field", "password"), ("key", "enter")]

    def test_none_means_the_default(self):
        """An entry saved before this existed has no sequence."""
        assert parse(None) == parse(DEFAULT)


class TestTwoStepLogins:
    def test_username_only_then_password_only(self):
        """Microsoft and Google: the account page, then the password
        page. Sending both at once puts the password into a page that
        has already navigated away."""
        assert parse("{USERNAME}{ENTER}") == [
            ("field", "username"), ("key", "enter")]
        assert parse("{PASSWORD}{ENTER}") == [
            ("field", "password"), ("key", "enter")]

    def test_a_delay_between_the_halves(self):
        """For a form that swaps itself in after the first field."""
        steps = parse("{USERNAME}{ENTER}{DELAY 800}{PASSWORD}{ENTER}")
        assert ("delay", 800) in steps

    @pytest.mark.parametrize("bad", ["{DELAY 0}", "{DELAY 999999}"])
    def test_an_unreasonable_delay_is_refused(self, bad):
        with pytest.raises(SequenceError):
            parse(bad)


class TestLiteralText:
    def test_text_around_tokens_is_kept(self):
        """A domain prefix is typed, not looked up."""
        assert parse(r"CORP\{USERNAME}{TAB}{PASSWORD}") == [
            ("text", "CORP\\"), ("field", "username"),
            ("key", "tab"), ("field", "password")]

    def test_trailing_text_is_kept(self):
        assert parse("{USERNAME}@corp.local") == [
            ("field", "username"), ("text", "@corp.local")]


class TestItRefuses:
    @pytest.mark.parametrize("bad,why", [
        ("{PASSWURD}", "a typo in a field name"),
        ("{}", "an empty token"),
        ("", "nothing at all"),
        ("   ", "only spaces"),
        ("{USERNAME", "an unclosed brace"),
        ("{USERNAME}{TAB", "an unclosed brace at the end"),
    ])
    def test_a_sequence_that_cannot_be_carried_out(self, bad, why):
        with pytest.raises(SequenceError):
            parse(bad)

    def test_a_typo_is_not_silently_skipped(self):
        """Dropping the step would type half a login and leave the user
        wondering which half went wrong."""
        with pytest.raises(SequenceError) as caught:
            parse("{USERNAME}{TAP}{PASSWORD}")
        assert "TAP" in str(caught.value)

    def test_an_unclosed_brace_is_not_typed_as_text(self):
        """`{PASSWORD` would otherwise type the word rather than the
        secret, which looks exactly like a wrong password."""
        with pytest.raises(SequenceError):
            parse("{USERNAME}{TAB}{PASSWORD")


class TestCaseAndSpacing:
    @pytest.mark.parametrize("written", [
        "{username}{tab}{password}", "{ UserName }{ Tab }{ PassWord }",
    ])
    def test_tokens_are_read_however_they_are_written(self, written):
        assert parse(written) == [("field", "username"), ("key", "tab"),
                                  ("field", "password")]

    def test_return_is_the_same_as_enter(self):
        assert parse("{RETURN}") == parse("{ENTER}")


class TestUses:
    def test_it_reports_which_fields_are_sent(self):
        assert uses("{USERNAME}{TAB}", "username")
        assert not uses("{USERNAME}{TAB}", "password")

    def test_a_broken_sequence_claims_nothing(self):
        """Used to decide whether to warn about sending a password, so
        it must not raise and must not claim a field on a bad parse."""
        assert not uses("{PASSWURD}", "password")


class TestDescribe:
    def test_it_reads_as_a_sentence(self):
        text = describe(DEFAULT)
        assert "username" in text and "password" in text
        assert "→" in text

    def test_it_never_contains_a_secret(self):
        """It goes in a confirmation prompt, on screen."""
        assert "hunter2" not in describe("{PASSWORD}")

    def test_a_broken_sequence_describes_the_problem(self):
        assert "not a known step" in describe("{NOPE}")


class TestValidate:
    def test_a_good_sequence_has_no_complaint(self):
        assert validate(DEFAULT) is None

    def test_a_bad_one_explains_itself(self):
        message = validate("{NOPE}")
        assert message and "NOPE" in message
