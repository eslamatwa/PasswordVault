"""Importing 1Password's 1PUX archive.

A 1PUX is a zip: ``export.data`` holds accounts, their vaults, and typed
items with custom sections, and ``files/`` holds the attachments. None of
that survives a column map, which is why 1Password's own CSV export drops
most of it.

The fixture is a real archive built from 1Password's documented shape, so
the tests read it the way the app will.

Two behaviours carry the design decisions and are asserted throughout:
items that are not logins are imported rather than skipped, and
attachments are named in the notes rather than extracted — this app stores
no files, and writing decrypted documents next to an encrypted vault would
be the opposite of the point.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile

from password_vault import export_import as ei
from password_vault import import_1pux as p1

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "1password.1pux")


def by_title(entries):
    return {e["title"]: e for e in entries}


class DetectionTests(unittest.TestCase):
    def test_the_fixture_is_recognised(self):
        self.assertTrue(p1.looks_like_1pux(FIXTURE))

    def test_a_plain_zip_is_not(self):
        fd, path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("readme.txt", "nothing to see")
        self.assertFalse(p1.looks_like_1pux(path))

    def test_a_file_that_is_not_a_zip_is_not(self):
        fd, path = tempfile.mkstemp(suffix=".1pux")
        with os.fdopen(fd, "w") as f:
            f.write("not a zip at all")
        self.addCleanup(os.unlink, path)
        self.assertFalse(p1.looks_like_1pux(path))


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.entries = ei.import_1pux(FIXTURE)
        self.by_title = by_title(self.entries)

    def test_active_items_from_every_vault_are_imported(self):
        # Four from Private plus one from Shared; the archived one is not.
        self.assertEqual(len(self.entries), 5)
        self.assertIn("Team mailbox", self.by_title)

    def test_login_fields_map_by_their_designation(self):
        jira = self.by_title["Jira"]
        self.assertEqual(jira["username"], "jsmith")
        self.assertEqual(jira["password"], "jira-p4ss")

    def test_the_primary_url_becomes_the_url(self):
        self.assertEqual(self.by_title["Jira"]["url"],
                         "https://jira.example.com")

    def test_additional_urls_are_kept_in_the_notes(self):
        self.assertIn("Also: https://jira-eu.example.com",
                      self.by_title["Jira"]["notes"])

    def test_a_tag_becomes_the_category(self):
        self.assertEqual(self.by_title["Jira"]["category"], "Work")

    def test_an_untagged_item_falls_back_to_its_vault_name(self):
        self.assertEqual(self.by_title["Wifi codes"]["category"], "Private")
        self.assertEqual(self.by_title["Team mailbox"]["category"],
                         "Shared")

    def test_a_favourite_becomes_pinned(self):
        self.assertTrue(self.by_title["Jira"]["pinned"])
        self.assertFalse(self.by_title["Team mailbox"]["pinned"])

    def test_custom_section_fields_are_kept(self):
        notes = self.by_title["Jira"]["notes"]
        self.assertIn("Employee ID: E-4417", notes)

    def test_a_totp_field_is_kept(self):
        """1PUX wraps a value in an object naming its type; a totp field
        would read as empty if only `string` were understood."""
        self.assertIn("JBSWY3DPEHPK3PXP", self.by_title["Jira"]["notes"])

    def test_the_original_note_survives_alongside_the_extras(self):
        self.assertIn("ticket tracker", self.by_title["Jira"]["notes"])

    def test_an_item_with_nothing_extra_keeps_clean_notes(self):
        self.assertEqual(self.by_title["Team mailbox"]["notes"], "")


class NonLoginTests(unittest.TestCase):
    """Only a login has a password. Skipping the rest would discard most
    of someone's vault without saying so."""

    def setUp(self):
        self.by_title = by_title(ei.import_1pux(FIXTURE))

    def test_a_secure_note_is_imported(self):
        note = self.by_title["Wifi codes"]
        self.assertEqual(note["password"], "")
        self.assertIn("guest wifi: hunter2", note["notes"])
        self.assertIn("Item type: Secure note", note["notes"])

    def test_a_card_keeps_its_fields(self):
        card = self.by_title["Travel card"]
        self.assertIn("Item type: Credit card", card["notes"])
        self.assertIn("Cardholder: J Smith", card["notes"])
        self.assertIn("4111111111111111", card["notes"])

    def test_an_archived_item_is_left_out(self):
        self.assertNotIn("Retired account", self.by_title)


class AttachmentTests(unittest.TestCase):
    def test_an_attachment_is_named_and_located(self):
        """The file is not extracted — this app stores none — so the entry
        has to say what was attached and where it still is."""
        doc = by_title(ei.import_1pux(FIXTURE))["Passport scan"]
        self.assertIn("passport-scan.pdf", doc["notes"])
        self.assertIn(".1pux", doc["notes"])

    def test_the_archive_still_holds_the_file(self):
        with zipfile.ZipFile(FIXTURE) as archive:
            names = archive.namelist()
        self.assertTrue(any(n.startswith("files/") for n in names))


class MalformedTests(unittest.TestCase):
    def _archive(self, members):
        fd, path = tempfile.mkstemp(suffix=".1pux")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return path

    def test_a_zip_without_an_export_is_refused(self):
        path = self._archive({"readme.txt": "nope"})
        with self.assertRaises(ValueError) as ctx:
            ei.import_1pux(path)
        self.assertIn("1Password export", str(ctx.exception))

    def test_an_export_that_is_not_json_is_refused(self):
        path = self._archive({"export.data": "not json"})
        with self.assertRaises(ValueError):
            ei.import_1pux(path)

    def test_json_that_is_not_a_1pux_export_is_refused(self):
        path = self._archive({"export.data": json.dumps({"items": []})})
        with self.assertRaises(ValueError):
            ei.import_1pux(path)

    def test_a_file_that_is_not_a_zip_is_refused(self):
        fd, path = tempfile.mkstemp(suffix=".1pux")
        with os.fdopen(fd, "w") as f:
            f.write("plain text")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(ValueError):
            ei.import_1pux(path)

    def test_malformed_vaults_and_items_are_skipped(self):
        payload = {"accounts": [
            "junk",
            {"vaults": ["junk", {"attrs": {"name": "V"}, "items": [
                "junk",
                {"item": {"state": "active", "categoryUuid": "001",
                          "details": {"loginFields": [
                              {"designation": "password",
                               "value": "p"}]},
                          "overview": {"title": "Good"}}}]}]}]}
        path = self._archive({"export.data": json.dumps(payload)})
        entries = ei.import_1pux(path)
        self.assertEqual([e["title"] for e in entries], ["Good"])

    def test_an_empty_export_yields_nothing(self):
        path = self._archive(
            {"export.data": json.dumps({"accounts": []})})
        self.assertEqual(ei.import_1pux(path), [])

    def test_a_declared_oversized_export_is_refused(self):
        """A zip can claim to be small and expand to gigabytes.

        The cap is patched on the module resolved the way the reader
        resolves it. `export_import.import_1pux` imports it inside the
        function, so it picks up whatever is in `sys.modules` at call
        time — and other test modules reload parts of the package, which
        can leave the copy imported at the top of this file stale. Patching
        that one would silently do nothing.
        """
        import importlib
        from unittest import mock

        reader = importlib.import_module("password_vault.import_1pux")
        path = self._archive(
            {"export.data": json.dumps({"accounts": []})})
        with mock.patch.object(reader, "MAX_EXPORT_BYTES", 1):
            with self.assertRaises(ValueError):
                ei.import_1pux(path)


class CompletionTests(unittest.TestCase):
    def test_entries_are_completed_with_ids_and_timestamps(self):
        for entry in ei.import_1pux(FIXTURE):
            with self.subTest(title=entry["title"]):
                self.assertTrue(entry["id"])
                self.assertTrue(entry["created_at"])
                self.assertTrue(entry["modified_at"])
                self.assertEqual(entry["color"], "default")

    def test_the_row_cap_is_applied(self):
        original = ei.MAX_IMPORT_ROWS
        ei.MAX_IMPORT_ROWS = 2
        try:
            self.assertEqual(len(ei.import_1pux(FIXTURE)), 2)
        finally:
            ei.MAX_IMPORT_ROWS = original


if __name__ == "__main__":
    unittest.main()
