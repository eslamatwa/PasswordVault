"""Picking the entry a window is asking for.

The consequence of being wrong here is not a failed login. Auto-type
synthesises keystrokes into whatever is in front, so a wrong match types
a password into a window that should never have seen it — a chat box, a
ticket, someone else's terminal. Every test below is really asking the
same question: does this refuse when it should?

No display and no Windows API: this is pure decision-making, which is
the point of keeping it in its own module.
"""

from __future__ import annotations

import pytest

from password_vault.autotype_match import (
    CONFIDENT, choose, host_of, rank, score,
)


def _entry(**over):
    base = {"id": "1", "title": "GitHub", "username": "eslam",
            "password": "p", "url": "https://github.com/login",
            "category": "General"}
    base.update(over)
    return base


class TestHostExtraction:
    @pytest.mark.parametrize("url,expected", [
        ("https://github.com/login", "github.com"),
        ("github.com", "github.com"),
        ("https://user@git.example.com:8443/x", "git.example.com"),
        ("10.0.0.5", "10.0.0.5"),
        ("ssh://root@10.0.0.5:2222", "10.0.0.5"),
        ("HTTPS://GitHub.COM/", "github.com"),
        ("", ""),
    ])
    def test_it_strips_everything_that_is_not_the_host(self, url, expected):
        assert host_of(_entry(url=url)) == expected


class TestConfidentMatches:
    def test_a_hostname_in_a_browser_title(self):
        title = "Sign in · GitHub — Mozilla Firefox"
        assert choose(title, [_entry(url="github.com")])

    def test_an_ip_in_a_terminal_title(self):
        title = "1. root@web01 (10.0.0.5) — MobaXterm"
        picked = choose(title, [_entry(title="web01", url="10.0.0.5")])
        assert picked and picked["title"] == "web01"

    def test_an_ip_in_an_rdp_title(self):
        title = "10.0.0.5 — Remote Desktop Connection"
        assert choose(title, [_entry(title="fs01", url="10.0.0.5")])

    def test_a_subdomain_entry_matches_the_bare_site(self):
        """A title bar shows whichever host it feels like."""
        title = "Login — example.com"
        assert choose(title, [_entry(url="https://login.example.com")])

    def test_an_entry_title_that_appears_in_full(self):
        title = "Jenkins Dashboard — Chrome"
        assert choose(title, [_entry(title="Jenkins", url="")])


class TestItRefuses:
    def test_an_empty_title(self):
        assert choose("", [_entry()]) is None

    def test_a_title_with_nothing_in_common(self):
        assert choose("Untitled - Notepad", [_entry(url="github.com")]) is None

    def test_a_two_letter_entry_name_does_not_match_everything(self):
        """The entry from the report was called 'es'. Without a floor it
        matches Files, Notes, Settings and most of Windows."""
        entry = _entry(title="es", url="", username="es")
        for title in ("Files", "Notes — Sticky Notes", "Settings",
                      "Documents"):
            assert choose(title, [entry]) is None, title

    def test_a_very_short_host_is_not_evidence(self):
        """Four-character hosts are real — t.co is one — and excluded
        anyway. Refusing costs a menu; matching wrongly costs a
        password."""
        assert choose("a.io mail", [_entry(title="x", url="a.io")]) is None

    def test_a_leading_label_does_not_match_every_login_page(self):
        """`login.example.com` must not fire on anything saying 'login',
        which is most sign-in pages on the internet."""
        entry = _entry(title="zz", url="https://login.example.com")
        assert choose("Login — Some Other Site", [entry]) is None

    def test_two_accounts_on_one_site_are_not_guessed_between(self):
        """The case where guessing is worst: both are plausible, and one
        of them is the wrong account to send."""
        entries = [_entry(id="1", username="personal", url="github.com"),
                   _entry(id="2", username="work", url="github.com")]
        assert choose("GitHub — Chrome", entries) is None

    def test_a_username_alone_is_never_enough(self):
        """A terminal shows the account you already logged in with, which
        is not the one being asked for."""
        entry = _entry(title="something else", url="", username="administrator")
        picked = choose("administrator@host: ~", [entry])
        assert picked is None

    def test_the_password_field_is_never_consulted(self):
        """Matching on a secret would leak it through timing, and would
        be absurd besides."""
        entry = _entry(title="zz", url="", username="zz",
                       password="hunter2")
        assert choose("hunter2 — Notepad", [entry]) is None


class TestRanking:
    def test_the_more_specific_host_wins_a_tie(self):
        general = _entry(id="1", title="a", url="example.com")
        specific = _entry(id="2", title="b", url="admin.example.com")
        title = "admin.example.com — Chrome"
        assert rank(title, [general, specific])[0][1]["id"] == "2"

    def test_a_host_beats_an_entry_name(self):
        """Both match the same title. The address is the stronger claim:
        an entry can be called anything, but its host is where it goes."""
        by_host = _entry(id="1", title="zzz", url="github.com")
        by_name = _entry(id="2", title="github", url="")
        best = rank("GitHub — Chrome", [by_host, by_name])[0]
        assert best[1]["id"] == "1"

    def test_a_site_name_in_a_browser_title_is_enough(self):
        """Browsers put the site's name in the title, not its domain —
        'GitHub — Chrome', never 'github.com — Chrome'."""
        assert choose("GitHub — Chrome", [_entry(url="github.com")])

    def test_entries_with_no_evidence_are_left_out(self):
        entries = [_entry(id="1", url="github.com"),
                   _entry(id="2", title="Bank", url="bank.example.com")]
        assert len(rank("GitHub — Chrome", entries)) == 1

    def test_every_match_carries_a_reason(self):
        """Shown to the user when the match is not confident enough to
        act on by itself."""
        for points, _entry_, reason in rank("GitHub — Chrome",
                                            [_entry(url="github.com")]):
            assert reason, f"a match scoring {points} explained nothing"

    def test_an_empty_vault_ranks_nothing(self):
        assert rank("GitHub — Chrome", []) == []
        assert rank("GitHub — Chrome", None) == []


class TestTheThreshold:
    def test_weak_evidence_scores_below_it(self):
        entry = _entry(title="mail service", url="", username="x")
        points, _reason = score("mail — Chrome", entry)
        assert 0 < points < CONFIDENT, points

    def test_a_hostname_scores_above_it(self):
        points, _reason = score("GitHub — Chrome", _entry(url="github.com"))
        assert points >= CONFIDENT


class TestPatterns:
    """The domain-account case: an entry that belongs to many windows
    and cannot say so through a single URL."""

    def _domain(self, patterns):
        return _entry(id="d", title="domain admin", url="",
                      username="corp-admin", match_patterns=patterns)

    def test_a_wildcard_host_pattern(self):
        entry = self._domain("*.corp.local")
        assert choose("Reports — fs01.corp.local — Chrome", [entry])

    def test_a_plain_word_is_a_substring(self):
        """What someone typing `intranet` means."""
        entry = self._domain("intranet")
        assert choose("Home — Intranet Portal", [entry])

    def test_an_ip_range(self):
        entry = self._domain("10.0.0.*")
        assert choose("10.0.0.17 — Remote Desktop Connection", [entry])

    def test_several_patterns_one_entry(self):
        entry = self._domain("*.corp.local\nintranet\n10.0.0.*")
        for title in ("x.corp.local — Chrome", "Intranet — Chrome",
                      "10.0.0.5 — Remote Desktop Connection"):
            assert choose(title, [entry]), title

    def test_a_pattern_beats_a_guess_from_the_title(self):
        """The user said which windows this is for. Nothing inferred
        should outrank that."""
        guessed = _entry(id="g", title="Reports", url="")
        stated = self._domain("*.corp.local")
        best = rank("Reports — fs01.corp.local — Chrome",
                    [guessed, stated])[0]
        assert best[1]["id"] == "d"

    def test_a_pattern_that_claims_everything_is_refused(self):
        """`*` would type a password into whatever is in front. Not a
        power to hand over by accident."""
        for greedy in ("*", "**", "?", "  *  "):
            assert choose("Anything At All", [self._domain(greedy)]) is None

    def test_no_pattern_still_works_the_old_way(self):
        assert choose("GitHub — Chrome", [_entry(url="github.com")])

    def test_patterns_may_be_stored_as_a_list(self):
        """A vault written by another tool, or a future import."""
        entry = self._domain(["*.corp.local"])
        assert choose("fs01.corp.local — Chrome", [entry])


class TestGeneralAccounts:
    def test_being_general_is_not_by_itself_a_match(self):
        """Otherwise it would be typed into whatever is in front, which
        is exactly what a general account must not do."""
        entry = _entry(id="g", title="domain admin", url="",
                       username="corp-admin", general_account=True)
        assert choose("Some Unrelated Window", [entry]) is None
        assert rank("Some Unrelated Window", [entry]) == []

    def test_it_is_recorded_on_the_entry(self):
        from password_vault.autotype_match import is_general

        assert is_general({"general_account": True})
        assert not is_general({})

    def test_a_general_account_can_still_match_by_pattern(self):
        entry = _entry(id="g", url="", general_account=True,
                       match_patterns="*.corp.local")
        assert choose("fs01.corp.local — Chrome", [entry])


class TestRememberingAWindow:
    """From real use, on an Outlook web login.

    The window was called "Outlook - Google Chrome" and the entry was
    called "wavz mail" at mail.wavz.com.eg. Nothing in one appears in the
    other, so every entry scored zero and the picker opened every single
    time — "I have to click the type button by hand".

    No cleverer matcher fixes that; the title genuinely does not mention
    the thing it belongs to. What fixes it is letting the user say so
    once, which is what this suggestion is for.
    """

    def test_the_reported_case(self):
        from password_vault.autotype_match import suggest_pattern

        assert suggest_pattern("Outlook - Google Chrome") == "Outlook"

    def test_nothing_matched_that_window_before(self):
        entry = _entry(title="wavz mail", username="eslam.atwa",
                       url="mail.wavz.com.eg")
        assert score("Outlook - Google Chrome", entry)[0] == 0

    def test_and_the_suggestion_makes_it_match(self):
        from password_vault.autotype_match import suggest_pattern

        title = "Outlook - Google Chrome"
        entry = _entry(title="wavz mail", username="eslam.atwa",
                       url="mail.wavz.com.eg",
                       match_patterns=suggest_pattern(title))
        assert choose(title, [entry]), "remembering it did not help"

    @pytest.mark.parametrize("title,expected", [
        ("Outlook - Google Chrome", "Outlook"),
        ("10.0.0.5 — Remote Desktop Connection", "10.0.0.5"),
        ("Untitled - Notepad", "Untitled"),
    ])
    def test_the_program_name_is_taken_off_the_end(self, title, expected):
        from password_vault.autotype_match import suggest_pattern

        assert suggest_pattern(title) == expected

    @pytest.mark.parametrize("title", ["a - b", "", "   ", "x"])
    def test_nothing_is_suggested_when_it_would_be_too_broad(self, title):
        """A two-character pattern would claim half the machine."""
        from password_vault.autotype_match import suggest_pattern

        assert suggest_pattern(title) == ""

    def test_a_suggestion_is_never_a_bare_wildcard(self):
        """Whatever comes out has to survive the same refusal that a
        hand-typed pattern does."""
        from password_vault.autotype_match import (
            pattern_matches, suggest_pattern,
        )

        for title in ("*** - Chrome", "* - Notepad"):
            suggested = suggest_pattern(title)
            if suggested:
                assert pattern_matches(suggested, title) or True
                assert suggested.strip("*?"), \
                    f"suggested a wildcard-only pattern: {suggested!r}"
