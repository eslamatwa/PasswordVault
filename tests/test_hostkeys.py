"""Knowing which machine answered.

The app opens dozens of sessions with one domain account and has never
checked that the machine answering is the one that answered last time.
The client's own `known_hosts` check helps on the second connection; on
the first it prints a fingerprint and asks yes/no, and a fingerprint with
nothing to compare against is a question with no answer.

Most of what follows is about the three outcomes, and especially about
not confusing two of them. "I could not check" is not "it matched", and
turning a failed scan into a refusal would make the feature unusable on
any network that blocks port 22 — while turning it into a pass would
make the whole thing decorative.
"""

from __future__ import annotations

import os

import pytest

from password_vault import hostkeys

# One real key, and the fingerprint `ssh-keygen -lf` prints for it. The
# algorithm is checked against a fixed pair rather than against itself.
GITLAB_ED25519 = (
    "AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzR"
    "df")
GITLAB_FINGERPRINT = "SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8"


class TestFingerprints:
    def test_it_matches_what_openssh_prints(self):
        """Verified against the fingerprint GitLab publishes on their own
        documentation, not against our own calculation."""
        assert hostkeys.fingerprint(GITLAB_ED25519) == GITLAB_FINGERPRINT

    def test_the_shape_is_the_one_a_client_shows(self):
        """It is compared by eye as well as by the app, so it has to be
        the same string the terminal prints."""
        fp = hostkeys.fingerprint(GITLAB_ED25519)
        assert fp.startswith("SHA256:")
        assert "=" not in fp, "padding is stripped in OpenSSH's form"
        assert len(fp) == len("SHA256:") + 43

    @pytest.mark.parametrize("junk", ["", "not base64!!", "===="])
    def test_rubbish_is_refused_rather_than_hashed(self, junk):
        """Hashing whatever arrived would produce a confident-looking
        fingerprint for something that is not a key."""
        with pytest.raises(ValueError):
            hostkeys.fingerprint(junk)

    def test_it_can_recognise_its_own_shape(self):
        assert hostkeys.is_fingerprint(GITLAB_FINGERPRINT)
        assert not hostkeys.is_fingerprint("MD5:aa:bb:cc")
        assert not hostkeys.is_fingerprint("")
        assert not hostkeys.is_fingerprint("SHA256:short")


class TestReadingAScan:
    SAMPLE = (
        "# gitlab.com:22 SSH-2.0-GitLab-SSHD\n"
        f"gitlab.com ssh-ed25519 {GITLAB_ED25519}\n"
        "# gitlab.com:22 SSH-2.0-GitLab-SSHD\n"
    )

    def test_it_reads_the_keys_and_drops_the_comments(self):
        """ssh-keyscan writes its progress to stdout as comments, and
        treating one as a key would invent a fingerprint for a banner."""
        found = hostkeys.parse_keyscan(self.SAMPLE)
        assert found == [("ssh-ed25519", GITLAB_FINGERPRINT)]

    def test_empty_output_yields_nothing(self):
        assert hostkeys.parse_keyscan("") == []
        assert hostkeys.parse_keyscan("# only a comment\n") == []

    def test_a_malformed_line_is_skipped_not_guessed_at(self):
        found = hostkeys.parse_keyscan(
            "host ssh-ed25519\nhost ssh-ed25519 !!!notbase64!!!\n")
        assert found == []

    def test_several_key_types_all_come_back(self):
        """A server offers more than one, and the client picks by its own
        preference — so all of them have to be candidates."""
        text = (f"h ssh-rsa {GITLAB_ED25519}\n"
                f"h ssh-ed25519 {GITLAB_ED25519}\n")
        assert len(hostkeys.parse_keyscan(text)) == 2


class TestComparing:
    OFFERED = [("ssh-rsa", "SHA256:" + "R" * 43),
               ("ssh-ed25519", GITLAB_FINGERPRINT)]

    def test_a_recorded_key_that_is_offered_matches(self):
        assert hostkeys.compare(GITLAB_FINGERPRINT,
                                self.OFFERED) == hostkeys.MATCH

    def test_matching_any_offered_key_counts(self):
        """A host that adds an ed25519 key beside its RSA one has not
        been replaced, and flagging that as an attack would train people
        to click through the warning that matters."""
        assert hostkeys.compare("SHA256:" + "R" * 43,
                                self.OFFERED) == hostkeys.MATCH

    def test_a_key_nobody_offered_is_a_mismatch(self):
        assert hostkeys.compare("SHA256:" + "X" * 43,
                                self.OFFERED) == hostkeys.MISMATCH

    def test_nothing_recorded_is_unknown_not_a_match(self):
        """The first connection. It must not silently pass as verified."""
        assert hostkeys.compare("", self.OFFERED) == hostkeys.UNKNOWN
        assert hostkeys.compare(None, self.OFFERED) == hostkeys.UNKNOWN

    def test_a_failed_scan_is_unreachable_not_a_mismatch(self):
        """This is the distinction the whole design turns on. A network
        that blocks port 22, or an ssh-keyscan too old for the server's
        key exchange, is not evidence of an attack — and treating it as
        one makes the feature unusable, which is how safety checks end up
        switched off."""
        assert hostkeys.compare(GITLAB_FINGERPRINT, []) == \
            hostkeys.UNREACHABLE


class TestWhichToRecord:
    def test_ed25519_is_preferred(self):
        """It is what a current OpenSSH negotiates, so it is the one the
        user will see quoted back at them."""
        offered = [("ssh-rsa", "SHA256:" + "R" * 43),
                   ("ssh-ed25519", GITLAB_FINGERPRINT)]
        assert hostkeys.preferred(offered) == GITLAB_FINGERPRINT

    def test_it_falls_back_rather_than_returning_nothing(self):
        offered = [("ssh-dss", "SHA256:" + "D" * 43)]
        assert hostkeys.preferred(offered) == "SHA256:" + "D" * 43

    def test_nothing_offered_gives_nothing(self):
        assert hostkeys.preferred([]) == ""


class TestKnownHosts:
    """Read, never written. That file belongs to the SSH client."""

    def test_a_plain_entry_is_found(self, tmp_path):
        path = tmp_path / "known_hosts"
        path.write_text(f"box.example.com ssh-ed25519 {GITLAB_ED25519}\n",
                        encoding="utf-8")
        found = hostkeys.in_known_hosts("box.example.com", 22, str(path))
        assert found == [("ssh-ed25519", GITLAB_FINGERPRINT)]

    def test_a_non_standard_port_is_bracketed(self, tmp_path):
        path = tmp_path / "known_hosts"
        path.write_text(
            f"[box.example.com]:2222 ssh-ed25519 {GITLAB_ED25519}\n",
            encoding="utf-8")
        assert hostkeys.in_known_hosts("box.example.com", 2222, str(path))
        assert not hostkeys.in_known_hosts("box.example.com", 22, str(path))

    def test_a_hashed_entry_is_skipped_rather_than_guessed(self, tmp_path):
        """Hashed entries cannot be matched by name without the salt, and
        a guess here would be false confidence about a host key."""
        path = tmp_path / "known_hosts"
        path.write_text(
            f"|1|abcdef=|ghijkl= ssh-ed25519 {GITLAB_ED25519}\n",
            encoding="utf-8")
        assert hostkeys.in_known_hosts("box.example.com", 22,
                                       str(path)) == []

    def test_several_names_on_one_line(self, tmp_path):
        path = tmp_path / "known_hosts"
        path.write_text(
            f"box.example.com,10.0.0.5 ssh-ed25519 {GITLAB_ED25519}\n",
            encoding="utf-8")
        assert hostkeys.in_known_hosts("10.0.0.5", 22, str(path))

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        assert hostkeys.in_known_hosts(
            "box", 22, str(tmp_path / "nope")) == []

    def test_comments_and_blank_lines_are_ignored(self, tmp_path):
        path = tmp_path / "known_hosts"
        path.write_text("# a comment\n\nbox ssh-ed25519 "
                        + GITLAB_ED25519 + "\n", encoding="utf-8")
        assert len(hostkeys.in_known_hosts("box", 22, str(path))) == 1


class TestScanning:
    def test_a_missing_tool_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(hostkeys, "_keyscan_path", lambda: None)
        found, problem = hostkeys.scan("box.example.com")
        assert found == []
        assert "ssh-keyscan" in problem

    def test_an_unreachable_host_reports_rather_than_hangs(self):
        """A launch cannot wait on a host that will never answer."""
        found, problem = hostkeys.scan("10.255.255.1", timeout=2)
        assert found == []
        assert problem

    @pytest.mark.skipif(
        os.environ.get("PASSWORDVAULT_NETWORK_TESTS") != "1",
        reason="needs outbound port 22; set PASSWORDVAULT_NETWORK_TESTS=1")
    def test_against_a_real_server(self):
        found, problem = hostkeys.scan("gitlab.com", timeout=10)
        assert not problem, problem
        assert hostkeys.preferred(found) == GITLAB_FINGERPRINT


class TestTheCheckBeforeLaunching:
    """What the app does with each verdict.

    The interesting one is UNREACHABLE. A check that blocks connections
    whenever it cannot reach port 22 is a check people turn off, and a
    check people turn off protects nobody.
    """

    @pytest.fixture
    def wired(self, app, monkeypatch):
        seen = {"launched": False, "alerts": [], "confirms": [],
                "recorded": None}
        entry = {"id": "h", "title": "web01", "username": "root",
                 "password": "p", "url": "10.0.0.5", "category": "Server"}
        app.data["entries"] = [entry]
        monkeypatch.setattr(app, "_alert",
                            lambda title, body="", **k:
                                seen["alerts"].append(title))
        monkeypatch.setattr(app, "_confirm",
                            lambda title, body="", **k:
                                seen["confirms"].append((title, k)))
        monkeypatch.setattr(app, "_save_guarded", lambda: True)
        app.settings["verify_host_keys"] = True
        return app, entry, seen

    def _proceed(self, seen):
        def go():
            seen["launched"] = True
        return go

    def test_a_match_connects_without_a_word(self, wired, monkeypatch):
        app, entry, seen = wired
        monkeypatch.setattr(
            app, "check_host_key",
            lambda *a: (hostkeys.MATCH, ""))
        app._with_host_check(entry, "10.0.0.5", 22, self._proceed(seen))
        assert seen["launched"]
        assert not seen["alerts"] and not seen["confirms"]

    def test_a_mismatch_refuses_and_says_so(self, wired, monkeypatch):
        """The case the whole feature exists for. A warning that can be
        clicked through would be no use here."""
        app, entry, seen = wired
        monkeypatch.setattr(
            app, "check_host_key",
            lambda *a: (hostkeys.MISMATCH, "the key changed"))
        app._with_host_check(entry, "10.0.0.5", 22, self._proceed(seen))
        assert not seen["launched"], "connected to a host whose key changed"
        assert seen["alerts"], "refused in silence"

    def test_an_unknown_host_asks_before_recording(self, wired,
                                                   monkeypatch):
        app, entry, seen = wired
        monkeypatch.setattr(
            app, "check_host_key",
            lambda *a: (hostkeys.UNKNOWN, "SHA256:" + "A" * 43))
        app._with_host_check(entry, "10.0.0.5", 22, self._proceed(seen))
        assert seen["confirms"], "recorded a key without asking"
        assert not seen["launched"], "connected before the user answered"

    def test_an_unreachable_host_still_connects(self, wired, monkeypatch):
        """Not being able to check is not evidence of anything."""
        app, entry, seen = wired
        monkeypatch.setattr(
            app, "check_host_key",
            lambda *a: (hostkeys.UNREACHABLE, "port 22 is blocked"))
        app._with_host_check(entry, "10.0.0.5", 22, self._proceed(seen))
        assert seen["launched"], "a blocked port stopped a connection"
        assert not seen["alerts"], "raised an alarm over a network problem"

    def test_the_check_is_skipped_when_switched_off(self, wired,
                                                    monkeypatch):
        app, entry, seen = wired
        app.settings["verify_host_keys"] = False
        called = []
        monkeypatch.setattr(app, "check_host_key",
                            lambda *a: called.append(a) or (None, ""))
        app._with_host_check(entry, "10.0.0.5", 22, self._proceed(seen))
        assert seen["launched"]
        assert called == [], "scanned a host with verification switched off"

    def test_recording_stores_the_fingerprint_on_the_entry(self, wired):
        app, entry, _seen = wired
        app.remember_host_key(entry, "SHA256:" + "B" * 43)
        assert entry["ssh_host_fingerprint"] == "SHA256:" + "B" * 43
