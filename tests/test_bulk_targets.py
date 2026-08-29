"""Reading a typed list of servers.

This is the expensive place to be wrong. A line read wrongly is not a
failed connection, it is a session opened to the *wrong machine* with a
domain account — which is the account this feature exists to use across
many machines. So the parsing is kept out of the dialog and tested here
without a window.

The rule throughout: refuse, never reshape. The same rule the single
session flow already follows, after silently rewriting host and username
corrupted real logins.
"""

from __future__ import annotations

import pytest

from password_vault.ui.bulk_targets import parse_hosts, split_target


def _reject(value, field):
    """Stand-in for the app's guard, refusing the shell characters."""
    if any(c in value for c in '&|<>^"`;'):
        return f"{field} has a shell character"
    if value.startswith("-"):
        return f"{field} cannot start with '-'"
    return None


class TestOneLine:
    @pytest.mark.parametrize("line,user,host,port", [
        ("10.0.0.5", "", "10.0.0.5", None),
        ("web01.example.com", "", "web01.example.com", None),
        ("root@10.0.0.5", "root", "10.0.0.5", None),
        ("root@10.0.0.5:2222", "root", "10.0.0.5", 2222),
        ("10.0.0.5:2222", "", "10.0.0.5", 2222),
        ("  root@box  ", "root", "box", None),
    ])
    def test_the_shapes_people_actually_type(self, line, user, host, port):
        assert split_target(line)[:3] == (user, host, port)

    def test_a_username_may_contain_an_at_sign(self):
        """Domain logins are often written as an address."""
        user, host, _port, error = split_target(
            "eslam@corp.local@10.0.0.5")
        assert (user, host) == ("eslam@corp.local", "10.0.0.5")
        assert error is None

    @pytest.mark.parametrize("line", ["box:notaport", "a:b:22", "box:"])
    def test_a_colon_that_is_not_a_port_is_refused(self, line):
        """The first version kept these in the host, which only defers
        the failure to ssh — where it is reported as the machine being
        unreachable, and the typo is nowhere in sight."""
        assert split_target(line)[3], f"{line!r} was accepted"

    def test_a_port_out_of_range_is_refused_not_clamped(self):
        _user, _host, port, error = split_target("box:99999")
        assert error, "an impossible port was accepted"
        assert port is None

    @pytest.mark.parametrize("line", ["@10.0.0.5", "root@", "root@:22"])
    def test_half_written_lines_are_refused(self, line):
        assert split_target(line)[3], f"{line!r} was accepted"


class TestABlockOfThem:
    def test_a_plain_list(self):
        targets, problems = parse_hosts("10.0.0.1\n10.0.0.2\n10.0.0.3")
        assert [x["host"] for x in targets] == ["10.0.0.1", "10.0.0.2",
                                                "10.0.0.3"]
        assert problems == []

    def test_blank_lines_and_comments_are_ignored(self):
        """A list is usually pasted from somewhere with notes in it."""
        targets, problems = parse_hosts(
            "# production\n10.0.0.1\n\n10.0.0.2   # the flaky one\n")
        assert [x["host"] for x in targets] == ["10.0.0.1", "10.0.0.2"]
        assert problems == []

    def test_the_default_account_fills_the_gaps(self):
        targets, _ = parse_hosts("10.0.0.1\nroot@10.0.0.2",
                                 default_user="domain\\eslam")
        assert targets[0]["user"] == "domain\\eslam"
        assert targets[1]["user"] == "root", \
            "a line naming its own user was overridden"

    def test_a_default_port_applies_where_none_is_given(self):
        targets, _ = parse_hosts("box\nbox2:2200", default_port=2022)
        assert [x["port"] for x in targets] == [2022, 2200]

    def test_duplicates_are_dropped(self):
        """The same machine twice means two sessions to it, silently."""
        targets, _ = parse_hosts("10.0.0.1\n10.0.0.1\nroot@10.0.0.1")
        assert len(targets) == 2, [x["host"] for x in targets]

    def test_the_same_host_with_different_users_is_not_a_duplicate(self):
        targets, _ = parse_hosts("root@box\nadmin@box")
        assert len(targets) == 2


class TestRefusals:
    def test_a_bad_line_does_not_cost_the_good_ones(self):
        """Twenty servers pasted in, one typo: the nineteen still go."""
        targets, problems = parse_hosts(
            "10.0.0.1\n10.0.0.2&calc\n10.0.0.3", check=_reject)
        assert [x["host"] for x in targets] == ["10.0.0.1", "10.0.0.3"]
        assert len(problems) == 1

    def test_a_refusal_names_the_line(self):
        """'Something was wrong' in a list of forty is not usable."""
        _targets, problems = parse_hosts(
            "ok1\nok2\nbad|host\n", check=_reject)
        assert problems and "line 3" in problems[0], problems

    def test_nothing_is_dropped_without_a_word(self):
        """A silently skipped server looks exactly like one that failed
        to connect, which is the worse of the two to debug."""
        text = "good\n-dash\nalso|bad\n"
        targets, problems = parse_hosts(text, check=_reject)
        assert len(targets) + len(problems) == 3

    def test_the_host_is_refused_whole_never_edited(self):
        targets, problems = parse_hosts("10.0.0.5&calc", check=_reject)
        assert targets == []
        assert problems, "a shell character slipped through"

    def test_the_username_is_checked_too(self):
        targets, problems = parse_hosts("root|whoami@box", check=_reject)
        assert targets == []
        assert problems

    def test_a_plus_in_a_username_is_fine(self):
        """`svc+deploy` is a real account that used to be mangled."""
        targets, problems = parse_hosts("svc+deploy@box", check=_reject)
        assert problems == []
        assert targets[0]["user"] == "svc+deploy"


class TestWhatComesOut:
    def test_each_target_carries_what_the_launcher_needs(self):
        targets, _ = parse_hosts("root@box:2222")
        assert targets[0]["host"] == "box"
        assert targets[0]["user"] == "root"
        assert targets[0]["port"] == 2222
        assert targets[0]["problem"] is None

    def test_a_typed_host_labels_itself(self):
        """Vault rows are named by entry title; typed hosts would all
        share the title of the one account behind them."""
        targets, _ = parse_hosts("web01.example.com")
        assert targets[0]["label"] == "web01.example.com"

    def test_an_empty_box_yields_nothing_and_no_complaint(self):
        assert parse_hosts("   \n\n  # nothing here\n") == ([], [])
