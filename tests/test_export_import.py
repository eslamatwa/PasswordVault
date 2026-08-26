"""Unit tests for password_vault.export_import."""

from __future__ import annotations

import datetime
import os
import shutil
import tempfile
import unittest

from password_vault import export_import as ei


def _entry(**over) -> dict:
    base = {
        "id": "abc",
        "title": "Bank",
        "username": "me",
        "password": "p@ss",
        "url": "https://bank.test",
        "category": "Banking",
        "notes": "note",
        "color": "blue",
        "created_at": "2024-01-01T10:00:00",
        "modified_at": "2024-02-02T11:00:00",
        "pinned": False,
    }
    base.update(over)
    return base


class FieldMapTests(unittest.TestCase):
    def test_columns_and_fields_stay_aligned(self):
        self.assertEqual(len(ei.EXPORT_COLS), len(ei._ENTRY_FIELDS))
        self.assertEqual(list(ei._FIELD_MAP), ei.EXPORT_COLS)
        self.assertEqual(list(ei._FIELD_MAP.values()), ei._ENTRY_FIELDS)


class FormulaEscapingTests(unittest.TestCase):
    def test_trigger_characters_are_prefixed(self):
        for value in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
            self.assertEqual(ei._escape_formula(value), "'" + value)

    def test_ordinary_values_untouched(self):
        for value in ("p@ss", "https://x.test", "", "a=b"):
            self.assertEqual(ei._escape_formula(value), value)

    def test_non_strings_pass_through(self):
        self.assertIs(ei._escape_formula(True), True)

    def test_unescape_is_the_inverse(self):
        for value in ("=1+1", "@x", "-x"):
            self.assertEqual(
                ei._unescape_formula(ei._escape_formula(value)), value)

    def test_unescape_keeps_a_real_leading_apostrophe(self):
        # Only an apostrophe that guards a trigger char is ours to remove.
        self.assertEqual(ei._unescape_formula("'quoted"), "'quoted")


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "vault.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_formula_is_neutralized_on_disk(self):
        ei.export_csv([_entry(password="=cmd|'/c calc'!A1")], self.path)
        with open(self.path, "r", encoding="utf-8-sig") as f:
            body = f.read()
        self.assertIn("'=cmd", body)
        self.assertNotIn(",=cmd", body)

    def test_roundtrip_restores_original_password(self):
        raw = "=cmd|'/c calc'!A1"
        ei.export_csv([_entry(password=raw)], self.path)
        out = ei.import_csv(self.path)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["password"], raw)

    def test_roundtrip_preserves_timestamps_and_pin(self):
        ei.export_csv([_entry(pinned=True)], self.path)
        out = ei.import_csv(self.path)[0]
        self.assertEqual(out["created_at"], "2024-01-01T10:00:00")
        self.assertEqual(out["modified_at"], "2024-02-02T11:00:00")
        self.assertTrue(out["pinned"])

    def test_unpinned_stays_unpinned(self):
        ei.export_csv([_entry(pinned=False)], self.path)
        self.assertFalse(ei.import_csv(self.path)[0]["pinned"])

    def test_missing_timestamp_falls_back_to_now(self):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            f.write("Title,Password\nNoDates,secret\n")
        out = ei.import_csv(self.path)[0]
        self.assertTrue(out["created_at"])
        self.assertTrue(out["modified_at"])
        self.assertEqual(out["category"], "General")
        self.assertEqual(out["color"], "default")

    def test_lowercase_headers_are_accepted(self):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            f.write("title,password,modified\nX,s,2023-05-05T00:00:00\n")
        out = ei.import_csv(self.path)[0]
        self.assertEqual(out["title"], "X")
        self.assertEqual(out["modified_at"], "2023-05-05T00:00:00")

    def test_rows_without_title_or_password_are_skipped(self):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            f.write("Title,Password\n,\nKeep,s\n")
        self.assertEqual(len(ei.import_csv(self.path)), 1)

    def test_import_is_capped(self):
        ei.export_csv([_entry(title=f"T{i}") for i in range(50)], self.path)
        original = ei.MAX_IMPORT_ROWS
        ei.MAX_IMPORT_ROWS = 10
        try:
            self.assertEqual(len(ei.import_csv(self.path)), 10)
        finally:
            ei.MAX_IMPORT_ROWS = original


@unittest.skipUnless(ei.HAS_OPENPYXL, "openpyxl not available")
class ExcelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "vault.xlsx")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip(self):
        raw = "=1+1"
        ei.export_excel([_entry(password=raw, pinned=True)], self.path)
        out = ei.import_excel(self.path)[0]
        self.assertEqual(out["password"], raw)
        self.assertEqual(out["title"], "Bank")
        self.assertTrue(out["pinned"])
        self.assertEqual(out["modified_at"], "2024-02-02T11:00:00")

    def test_datetime_cells_become_iso(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Title", "Password", "Created"])
        ws.append(["X", "s", datetime.datetime(2024, 3, 4, 5, 6, 7)])
        wb.save(self.path)
        wb.close()
        out = ei.import_excel(self.path)[0]
        self.assertEqual(out["created_at"], "2024-03-04T05:06:07")

    def test_empty_workbook_yields_nothing(self):
        import openpyxl
        wb = openpyxl.Workbook()
        wb.save(self.path)
        wb.close()
        self.assertEqual(ei.import_excel(self.path), [])

    def test_import_is_capped(self):
        ei.export_excel([_entry(title=f"T{i}") for i in range(50)], self.path)
        original = ei.MAX_IMPORT_ROWS
        ei.MAX_IMPORT_ROWS = 10
        try:
            self.assertEqual(len(ei.import_excel(self.path)), 10)
        finally:
            ei.MAX_IMPORT_ROWS = original


if __name__ == "__main__":
    unittest.main()
