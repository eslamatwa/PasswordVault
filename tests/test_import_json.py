"""Importing Bitwarden's JSON export.

The CSV profile already reads Bitwarden's flat export. This covers what
that format cannot carry: folders joined by id, several URIs per item,
typed items that are not logins, and per-item custom fields.

The rule is the same as for the CSV profiles — anything with no home here
goes into the notes rather than being dropped — so most of these tests are
about what survives the import, not about what maps cleanly.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from password_vault import export_import as ei
from password_vault import import_json as ij

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "bitwarden.json")


def by_title(entries):
    return {e["title"]: e for e in entries}


class DetectionTests(unittest.TestCase):
    def test_a_real_export_is_recognised(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.assertTrue(ij.looks_like_bitwarden_json(json.load(f)))

    def test_other_json_is_not(self):
        for payload in ({"hello": "world"}, [], "text", 7, None,
                        {"items": "not a list"}):
            with self.subTest(payload=payload):
                self.assertFalse(ij.looks_like_bitwarden_json(payload))

    def test_an_empty_export_is_still_recognised(self):
        self.assertTrue(
            ij.looks_like_bitwarden_json({"items": [], "folders": []}))

    def test_an_encrypted_export_is_refused_with_a_useful_message(self):
        """Bitwarden can export a password-protected file this cannot read.

        Failing with "not a Bitwarden export" would send the user looking
        for the wrong problem.
        """
        with self.assertRaises(ValueError) as ctx:
            ij.parse_items({"encrypted": True, "items": [],
                            "data": "..."})
        self.assertIn("password-protected", str(ctx.exception))


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_json(FIXTURE)
        self.by_title = by_title(self.entries)

    def test_every_item_is_imported_including_non_logins(self):
        self.assertEqual(len(self.entries), 5)

    def test_login_fields_map_directly(self):
        jira = self.by_title["Jira"]
        self.assertEqual(jira["username"], "jsmith")
        self.assertEqual(jira["password"], "jira-p4ss")

    def test_the_first_uri_becomes_the_url(self):
        self.assertEqual(self.by_title["Jira"]["url"],
                         "https://jira.example.com")

    def test_extra_uris_are_kept_in_the_notes(self):
        """A CSV export keeps one URI. The JSON has them all."""
        self.assertIn("Also: https://jira-eu.example.com",
                      self.by_title["Jira"]["notes"])

    def test_folders_become_categories_by_id(self):
        self.assertEqual(self.by_title["Jira"]["category"], "Work")
        self.assertEqual(self.by_title["Wifi codes"]["category"], "Home")

    def test_an_item_with_no_folder_falls_back_to_general(self):
        self.assertEqual(self.by_title["Personal Mail"]["category"],
                         "General")

    def test_favorite_becomes_pinned(self):
        self.assertTrue(self.by_title["Jira"]["pinned"])
        self.assertFalse(self.by_title["Personal Mail"]["pinned"])

    def test_totp_is_kept(self):
        self.assertIn("TOTP: JBSWY3DPEHPK3PXP",
                      self.by_title["Jira"]["notes"])

    def test_custom_fields_are_kept_under_their_own_names(self):
        notes = self.by_title["Jira"]["notes"]
        self.assertIn("Employee ID: E-4417", notes)
        self.assertIn("Recovery code: abcd-efgh", notes)

    def test_the_original_note_survives_alongside_the_extras(self):
        self.assertIn("ticket tracker", self.by_title["Jira"]["notes"])

    def test_an_item_with_nothing_extra_keeps_clean_notes(self):
        self.assertEqual(self.by_title["Personal Mail"]["notes"], "")

    def test_a_secure_note_is_imported_rather_than_skipped(self):
        """It has no password, so a login-only importer would drop it."""
        note = self.by_title["Wifi codes"]
        self.assertEqual(note["password"], "")
        self.assertIn("guest network: hunter2", note["notes"])
        self.assertIn("Item type: Secure note", note["notes"])

    def test_a_card_keeps_its_details_in_the_notes(self):
        card = self.by_title["Travel card"]
        self.assertIn("Cardholder: J Smith", card["notes"])
        self.assertIn("Number: 4111111111111111", card["notes"])
        self.assertIn("Security code: 123", card["notes"])
        self.assertIn("Item type: Card", card["notes"])

    def test_attachments_are_reported_as_missing_not_ignored(self):
        """A JSON export references attachments but does not contain them,
        so the entry has to say the file did not come along."""
        self.assertIn("attachment", self.by_title["With attachment"]["notes"])

    def test_entries_are_completed_with_ids_and_timestamps(self):
        for entry in self.entries:
            with self.subTest(title=entry["title"]):
                self.assertTrue(entry["id"])
                self.assertTrue(entry["created_at"])
                self.assertTrue(entry["modified_at"])
                self.assertEqual(entry["color"], "default")


class MalformedTests(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_a_file_that_is_not_json_is_refused(self):
        with self.assertRaises(ValueError):
            ei.import_json(self._write("not json at all"))

    def test_json_that_is_not_a_bitwarden_export_is_refused(self):
        with self.assertRaises(ValueError):
            ei.import_json(self._write('{"something": "else"}'))

    def test_items_that_are_not_objects_are_skipped(self):
        path = self._write(json.dumps(
            {"folders": [], "items": [
                "junk", 7,
                {"type": 1, "name": "Good",
                 "login": {"username": "u", "password": "p"}}]}))
        entries = ei.import_json(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Good")

    def test_an_item_with_no_login_block_does_not_raise(self):
        path = self._write(json.dumps(
            {"folders": [], "items": [{"type": 1, "name": "Bare"}]}))
        entries = ei.import_json(path)
        self.assertEqual(entries[0]["username"], "")
        self.assertEqual(entries[0]["password"], "")

    def test_a_completely_empty_item_is_dropped(self):
        path = self._write(json.dumps(
            {"folders": [], "items": [{"type": 1, "name": ""}]}))
        self.assertEqual(ei.import_json(path), [])

    def test_a_row_cap_is_applied(self):
        many = [{"type": 1, "name": f"Item {i}",
                 "login": {"username": "u", "password": "p"}}
                for i in range(5)]
        path = self._write(json.dumps({"folders": [], "items": many}))
        original = ei.MAX_IMPORT_ROWS
        ei.MAX_IMPORT_ROWS = 3
        try:
            self.assertEqual(len(ei.import_json(path)), 3)
        finally:
            ei.MAX_IMPORT_ROWS = original


if __name__ == "__main__":
    unittest.main()
