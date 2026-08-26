"""Unit tests for password_vault.security helpers."""

from __future__ import annotations

import unittest

import datetime

from password_vault.security import (
    calculate_security_score, entry_identity, find_duplicate_passwords,
    find_new_entries, generate_password, group_by_password,
    is_password_reused, password_age_text, password_hash, safe_url,
)


class SafeUrlTests(unittest.TestCase):
    def test_http_and_https_pass_through(self):
        for url in ("http://a.test", "https://a.test/x?q=1#f",
                    "HTTPS://A.test"):
            self.assertEqual(safe_url(url), url)

    def test_schemeless_host_gets_https(self):
        self.assertEqual(safe_url("example.com"), "https://example.com")
        self.assertEqual(safe_url("example.com/login"),
                         "https://example.com/login")

    def test_schemeless_host_with_port(self):
        self.assertEqual(safe_url("example.com:8080/x"),
                         "https://example.com:8080/x")

    def test_dangerous_schemes_refused(self):
        for url in ("file:///C:/Windows/system.ini",
                    "javascript:alert(1)",
                    "data:text/html,<script>x</script>",
                    "ms-msdt:/id PCWDiagnostic",
                    "vbscript:msgbox",
                    "mailto:a@b.test",
                    "ftp://host/x",
                    r"C:\Windows\System32\calc.exe",
                    r"\\server\share\file.exe",
                    "/etc/passwd"):
            self.assertIsNone(safe_url(url), url)

    def test_http_without_host_refused(self):
        self.assertIsNone(safe_url("http:notahost"))
        self.assertIsNone(safe_url("https://"))

    def test_blank_input_refused(self):
        for url in ("", "   ", None):
            self.assertIsNone(safe_url(url))

    def test_control_characters_refused(self):
        self.assertIsNone(safe_url("https://a.test\r\nHeader: x"))
        self.assertIsNone(safe_url("https://a.test\tx"))

    def test_surrounding_whitespace_tolerated(self):
        self.assertEqual(safe_url("  https://a.test  "), "https://a.test")


def _entry(eid, title, username="u", password="pw"):
    return {"id": eid, "title": title, "username": username,
            "password": password}


class DuplicatePolicyTests(unittest.TestCase):
    def test_grouping_ignores_entries_without_a_password(self):
        entries = [_entry("1", "A", password=""), _entry("2", "B")]
        groups = group_by_password(entries)
        self.assertEqual(len(groups), 1)

    def test_duplicates_are_grouped_by_secret(self):
        entries = [_entry("1", "A", password="same"),
                   _entry("2", "B", password="same"),
                   _entry("3", "C", password="other")]
        dups = find_duplicate_passwords(entries)
        self.assertEqual(len(dups), 1)
        self.assertEqual(len(next(iter(dups.values()))), 2)

    def test_hash_is_stable_and_hides_the_secret(self):
        digest = password_hash("hunter2")
        self.assertEqual(digest, password_hash("hunter2"))
        self.assertNotIn("hunter2", digest)
        self.assertNotEqual(digest, password_hash("hunter3"))

    def test_reuse_detection_skips_the_entry_being_edited(self):
        entries = [_entry("1", "A", password="same")]
        self.assertTrue(is_password_reused(entries, "same"))
        self.assertFalse(is_password_reused(entries, "same",
                                            exclude_id="1"))
        self.assertFalse(is_password_reused(entries, ""))

    def test_import_identity_ignores_case_and_padding(self):
        self.assertEqual(entry_identity({"title": " Bank ", "username": "ME"}),
                         entry_identity({"title": "bank", "username": "me"}))

    def test_new_entries_excludes_known_accounts(self):
        existing = [_entry("1", "Bank", "me")]
        candidates = [_entry("x", "bank", "ME", password="rotated"),
                      _entry("y", "Other", "me")]
        new = find_new_entries(existing, candidates)
        self.assertEqual([e["title"] for e in new], ["Other"])

    def test_new_entries_dedupes_within_the_import_itself(self):
        candidates = [_entry("x", "Same", "me"), _entry("y", "Same", "me")]
        self.assertEqual(len(find_new_entries([], candidates)), 1)


class SecurityScoreTests(unittest.TestCase):
    def test_duplicates_counts_extra_copies_only(self):
        entries = [_entry(str(i), f"E{i}", password="shared")
                   for i in range(3)]
        _, stats = calculate_security_score(entries)
        self.assertEqual(stats["duplicates"], 2)

    def test_no_duplicates_scores_none(self):
        entries = [_entry("1", "A", password="Aa1!Aa1!Aa1!"),
                   _entry("2", "B", password="Bb2@Bb2@Bb2@")]
        score, stats = calculate_security_score(entries)
        self.assertEqual(stats["duplicates"], 0)
        self.assertEqual(score, 100)

    def test_empty_vault_is_perfect(self):
        score, stats = calculate_security_score([])
        self.assertEqual(score, 100)
        self.assertEqual(stats["total"], 0)


class PasswordAgeTests(unittest.TestCase):
    def test_future_timestamp_is_flagged(self):
        future = (datetime.datetime.now()
                  + datetime.timedelta(days=3)).isoformat()
        text, _ = password_age_text(future)
        self.assertEqual(text, "Future?")

    def test_today(self):
        text, _ = password_age_text(datetime.datetime.now().isoformat())
        self.assertEqual(text, "Today")

    def test_old_password_reported_in_years(self):
        old = (datetime.datetime.now()
               - datetime.timedelta(days=800)).isoformat()
        text, _ = password_age_text(old)
        self.assertEqual(text, "2y")

    def test_garbage_timestamp_is_silent(self):
        self.assertEqual(password_age_text("not-a-date")[0], "")
        self.assertEqual(password_age_text(None)[0], "")


class GeneratorLengthTests(unittest.TestCase):
    def test_length_shorter_than_class_count_is_honored(self):
        for length in (1, 2, 3):
            pw = generate_password(length, True, True, True, True)
            self.assertEqual(len(pw), length, pw)

    def test_zero_and_negative_length(self):
        self.assertEqual(generate_password(0), "")
        self.assertEqual(generate_password(-5), "")

    def test_requested_length_is_exact(self):
        for length in (4, 16, 64, 128):
            self.assertEqual(len(generate_password(length)), length)


if __name__ == "__main__":
    unittest.main()
