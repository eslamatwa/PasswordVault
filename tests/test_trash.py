"""Tests for the Recycle Bin removal helper.

Restoring or permanently deleting one row has to take that row and nothing
else. Matching on the id alone was not enough: entries deleted before ids
existed all share a missing id, so one restore took the rest with it.
"""

from __future__ import annotations

import unittest

from password_vault.ui.dialogs.trash import _without


class WithoutTests(unittest.TestCase):
    def test_removes_the_row_with_a_unique_id(self):
        a = {"id": "1", "title": "a"}
        b = {"id": "2", "title": "b"}
        self.assertEqual(_without([a, b], a), [b])

    def test_keeps_every_other_row_when_ids_are_missing(self):
        a = {"title": "a"}
        b = {"title": "b"}
        c = {"title": "c"}
        self.assertEqual(_without([a, b, c], b), [a, c])

    def test_removes_only_one_of_two_rows_sharing_an_id(self):
        a = {"id": "dup", "title": "older"}
        b = {"id": "dup", "title": "newer"}
        self.assertEqual(_without([a, b], b), [a])

    def test_equal_rows_are_distinguished_by_identity(self):
        # Two trash rows can compare equal field for field; only the one
        # the card was built from may be dropped.
        a = {"title": "same"}
        b = {"title": "same"}
        result = _without([a, b], a)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], b)

    def test_a_row_that_is_not_in_the_bin_changes_nothing(self):
        a = {"id": "1"}
        self.assertEqual(_without([a], {"id": "2"}), [a])

    def test_empty_bin_stays_empty(self):
        self.assertEqual(_without([], {"id": "1"}), [])


if __name__ == "__main__":
    unittest.main()
