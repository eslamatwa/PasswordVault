"""Unit tests for pure helpers in password_vault.ui.widgets."""

from __future__ import annotations

import unittest

from password_vault.ui.widgets import (
    elide, filter_entries, sort_entries_pinned_first,
)


class ElideTests(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(elide("Bank", 10), "Bank")

    def test_exact_limit_is_untouched(self):
        self.assertEqual(elide("abcde", 5), "abcde")

    def test_long_text_is_shortened_to_the_limit(self):
        out = elide("abcdefghij", 5)
        self.assertEqual(len(out), 5)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out, "abcd…")

    def test_trailing_space_is_not_left_before_the_ellipsis(self):
        self.assertEqual(elide("ab cdef", 4), "ab…")

    def test_empty_and_none(self):
        self.assertEqual(elide("", 5), "")
        self.assertEqual(elide(None, 5), "")


ENTRIES = [
    {"title": "Bank", "username": "me", "url": "https://bank.test",
     "category": "Banking", "notes": "vacation fund"},
    {"title": "Mail", "username": "eslam", "url": "https://mail.test",
     "category": "Email", "notes": ""},
    {"title": "Server 01", "username": "root", "url": "10.0.0.1",
     "category": "Server", "notes": "prod"},
]


class FilterEntriesTests(unittest.TestCase):
    def test_all_category_and_empty_query_returns_everything(self):
        self.assertEqual(len(filter_entries(ENTRIES, "All", "")), 3)

    def test_category_filter(self):
        out = filter_entries(ENTRIES, "Email", "")
        self.assertEqual([e["title"] for e in out], ["Mail"])

    def test_query_is_case_insensitive(self):
        self.assertEqual(len(filter_entries(ENTRIES, "All", "BANK")), 1)

    def test_query_matches_the_category_field(self):
        # The Mini Vault used to omit this field, so the same query gave
        # different results in the two windows.
        out = filter_entries(ENTRIES, "All", "server")
        self.assertEqual(len(out), 1)

    def test_query_matches_notes_and_url(self):
        self.assertEqual(len(filter_entries(ENTRIES, "All", "vacation")), 1)
        self.assertEqual(len(filter_entries(ENTRIES, "All", "10.0.0")), 1)

    def test_category_and_query_combine(self):
        self.assertEqual(len(filter_entries(ENTRIES, "Banking", "mail")), 0)

    def test_whitespace_only_query_is_ignored(self):
        self.assertEqual(len(filter_entries(ENTRIES, "All", "   ")), 3)

    def test_missing_fields_do_not_raise(self):
        self.assertEqual(filter_entries([{}], "All", "x"), [])

    def test_input_list_is_not_mutated(self):
        original = list(ENTRIES)
        filter_entries(ENTRIES, "Email", "mail")
        self.assertEqual(ENTRIES, original)


class SortEntriesPinnedFirstTests(unittest.TestCase):
    def test_pinned_entries_come_first(self):
        entries = [{"title": "b"}, {"title": "a", "pinned": True}]
        out = sort_entries_pinned_first(entries)
        self.assertEqual([e["title"] for e in out], ["a", "b"])

    def test_ties_are_broken_case_insensitively_by_title(self):
        entries = [{"title": "beta"}, {"title": "Alpha"}, {"title": "gamma"}]
        out = sort_entries_pinned_first(entries)
        self.assertEqual([e["title"] for e in out],
                          ["Alpha", "beta", "gamma"])

    def test_pinned_group_is_also_sorted_by_title(self):
        entries = [{"title": "z", "pinned": True},
                   {"title": "a", "pinned": True},
                   {"title": "m"}]
        out = sort_entries_pinned_first(entries)
        self.assertEqual([e["title"] for e in out], ["a", "z", "m"])

    def test_missing_keys_are_treated_as_unpinned_and_untitled(self):
        out = sort_entries_pinned_first([{}, {"title": "a", "pinned": True}])
        self.assertEqual(out[0]["title"], "a")

    def test_input_list_is_not_mutated(self):
        entries = [{"title": "b"}, {"title": "a", "pinned": True}]
        snapshot = list(entries)
        sort_entries_pinned_first(entries)
        self.assertEqual(entries, snapshot)


if __name__ == "__main__":
    unittest.main()
