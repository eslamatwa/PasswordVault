"""Importing a vault exported by another password manager.

Each supported source has a fixture in ``tests/fixtures`` holding a real
header row for that application, so a format change upstream shows up as a
detection failure here rather than as a vault full of blank entries.

Two behaviours are asserted throughout, because they are the decisions the
feature turns on:

* detection names a format from the header row alone, and the caller can
  override it;
* a column with no home in this app is folded into the notes, never
  dropped without a word.
"""

from __future__ import annotations

import os
import unittest

from password_vault import export_import as ei
from password_vault import import_profiles as ip

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


class DetectionTests(unittest.TestCase):
    def test_each_fixture_is_detected_as_its_own_format(self):
        expected = {
            "chrome.csv": "chrome",
            "bitwarden.csv": "bitwarden",
            "lastpass.csv": "lastpass",
            "1password.csv": "1password",
            "keepass.csv": "keepass",
            "firefox.csv": "firefox",
        }
        for filename, key in expected.items():
            with self.subTest(filename=filename):
                headers = ei.read_headers(fixture(filename))
                self.assertEqual(ip.detect(headers).key, key)

    def test_our_own_export_is_detected_as_native(self):
        self.assertEqual(ip.detect(ei.EXPORT_COLS).key, "native")

    def test_an_unrecognised_header_row_falls_back_to_native(self):
        self.assertEqual(ip.detect(["alpha", "beta", "gamma"]).key,
                         "native")

    def test_detection_ignores_case_and_padding(self):
        self.assertEqual(
            ip.detect(["  NAME ", "URL", "Username", "PASSWORD"]).key,
            "chrome")

    def test_an_empty_header_row_falls_back_to_native(self):
        self.assertEqual(ip.detect([]).key, "native")

    def test_a_partial_match_does_not_displace_native(self):
        # "url" and "password" alone are too weak a signal to claim a
        # format; a hand-made sheet must not be read as Chrome's.
        self.assertEqual(ip.detect(["url", "password"]).key, "native")

    def test_describe_reports_the_match_strength(self):
        headers = ei.read_headers(fixture("chrome.csv"))
        text = ip.describe(ip.detect(headers), headers)
        self.assertIn("Chrome", text)
        self.assertIn("100%", text)


class ChromeTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_csv(fixture("chrome.csv"))

    def test_all_rows_are_read(self):
        self.assertEqual(len(self.entries), 2)

    def test_columns_land_in_the_right_fields(self):
        e = self.entries[0]
        self.assertEqual(e["title"], "GitHub")
        self.assertEqual(e["url"], "https://github.com")
        self.assertEqual(e["username"], "octocat")
        self.assertEqual(e["password"], "gh-p4ss")
        self.assertEqual(e["notes"], "work account")

    def test_missing_category_defaults(self):
        self.assertEqual(self.entries[0]["category"], "General")


class BitwardenTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_csv(fixture("bitwarden.csv"))

    def test_login_columns_are_mapped(self):
        e = self.entries[0]
        self.assertEqual(e["title"], "Jira")
        self.assertEqual(e["username"], "jsmith")
        self.assertEqual(e["password"], "jira-p4ss")
        self.assertEqual(e["url"], "https://jira.example.com")

    def test_folder_becomes_the_category(self):
        self.assertEqual(self.entries[0]["category"], "Work")
        self.assertEqual(self.entries[1]["category"], "General")

    def test_favorite_becomes_pinned(self):
        self.assertTrue(self.entries[0]["pinned"])
        self.assertFalse(self.entries[1]["pinned"])

    def test_totp_is_kept_in_the_notes(self):
        # A TOTP secret is a credential. Dropping it silently would lose
        # the user's second factor with no way to notice.
        self.assertIn("TOTP: JBSWY3DPEHPK3PXP", self.entries[0]["notes"])

    def test_custom_fields_are_kept_in_the_notes(self):
        self.assertIn("Custom fields: dept: eng",
                      self.entries[0]["notes"])

    def test_the_original_note_is_kept_alongside_the_extras(self):
        self.assertIn("ticket tracker", self.entries[0]["notes"])

    def test_an_entry_without_extras_keeps_empty_notes(self):
        self.assertEqual(self.entries[1]["notes"], "")


class LastPassTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_csv(fixture("lastpass.csv"))

    def test_extra_becomes_the_notes(self):
        self.assertIn("security questions", self.entries[0]["notes"])

    def test_grouping_becomes_the_category(self):
        self.assertEqual(self.entries[0]["category"], "Finance")

    def test_fav_becomes_pinned(self):
        self.assertTrue(self.entries[0]["pinned"])
        self.assertFalse(self.entries[1]["pinned"])

    def test_totp_is_kept(self):
        self.assertIn("TOTP: LPTOTPSECRET", self.entries[1]["notes"])


class OnePasswordTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_csv(fixture("1password.csv"))

    def test_tags_become_the_category(self):
        self.assertEqual(self.entries[0]["category"], "Home")

    def test_favorite_true_and_false_are_read(self):
        self.assertFalse(self.entries[0]["pinned"])
        self.assertTrue(self.entries[1]["pinned"])

    def test_otpauth_is_kept(self):
        self.assertIn("TOTP: otpauth://totp/x", self.entries[1]["notes"])


class KeePassTests(unittest.TestCase):
    def test_two_word_headers_are_mapped(self):
        entries = ei.import_csv(fixture("keepass.csv"))
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["title"], "NAS")
        self.assertEqual(e["username"], "admin")
        self.assertEqual(e["url"], "http://nas.local")
        self.assertEqual(e["category"], "Home")


class FirefoxTests(unittest.TestCase):
    def test_a_row_with_no_title_column_still_imports(self):
        # Firefox exports no name at all; the row survives on its password.
        entries = ei.import_csv(fixture("firefox.csv"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["password"], "fx-p4ss")
        self.assertEqual(entries[0]["username"], "poster")


class OverrideTests(unittest.TestCase):
    def test_an_explicit_profile_overrides_detection(self):
        # Read a Chrome file as LastPass: both have url/username/password,
        # but "name" is a title in one and absent from the other's map.
        entries = ei.import_csv(fixture("chrome.csv"), ip.LASTPASS)
        self.assertEqual(entries[0]["title"], "GitHub")
        # Chrome's "note" is not a LastPass column, so it does not arrive.
        self.assertEqual(entries[0]["notes"], "")

    def test_reading_under_the_wrong_profile_yields_nothing_usable(self):
        # KeePass columns share nothing with Bitwarden's, so every row is
        # skipped as empty rather than mapped to the wrong fields.
        entries = ei.import_csv(fixture("keepass.csv"), ip.BITWARDEN)
        self.assertEqual(entries, [])


class UnmappedHeaderTests(unittest.TestCase):
    def test_columns_with_no_mapping_are_reported(self):
        headers = ei.read_headers(fixture("firefox.csv"))
        leftover = ip.unmapped_headers(ip.FIREFOX, headers)
        self.assertIn("timecreated", leftover)
        self.assertIn("guid", leftover)
        self.assertNotIn("password", leftover)

    def test_a_fully_mapped_file_reports_nothing(self):
        headers = ei.read_headers(fixture("chrome.csv"))
        self.assertEqual(ip.unmapped_headers(ip.CHROME, headers), [])


class ReadHeadersTests(unittest.TestCase):
    def test_headers_are_returned_without_parsing_the_body(self):
        self.assertEqual(
            ei.read_headers(fixture("chrome.csv")),
            ["name", "url", "username", "password", "note"])

    def test_an_empty_file_returns_no_headers(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
                "w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            self.assertEqual(ei.read_headers(path), [])
        finally:
            os.unlink(path)


class NativeRoundTripTests(unittest.TestCase):
    """The profile work must not change how our own export reads back."""

    def test_native_export_still_round_trips(self):
        import tempfile
        entries = [{
            "id": "x", "title": "Site", "username": "u",
            "password": "=danger", "url": "https://example.com",
            "category": "Work", "notes": "n", "color": "blue",
            "pinned": True, "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-02-02T00:00:00",
        }]
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "out.csv")
        ei.export_csv(entries, path)
        back = ei.import_csv(path)
        self.assertEqual(len(back), 1)
        got = back[0]
        for key in ("title", "username", "password", "url", "category",
                    "notes", "color", "pinned", "created_at",
                    "modified_at"):
            self.assertEqual(got[key], entries[0][key], key)


if __name__ == "__main__":
    unittest.main()
