"""Unit tests for the single-instance guard."""

from __future__ import annotations

import sys
import unittest
import uuid

from password_vault import instance_lock


class AcquireTests(unittest.TestCase):
    def setUp(self):
        # A unique name per test so a real running app never interferes.
        self.name = f"Local\\PasswordVault-test-{uuid.uuid4().hex}"

    def test_first_acquire_succeeds(self):
        self.assertTrue(instance_lock.acquire(self.name))

    @unittest.skipUnless(sys.platform == "win32",
                         "named mutex semantics are Windows-specific")
    def test_second_acquire_is_refused(self):
        self.assertTrue(instance_lock.acquire(self.name))
        self.assertFalse(instance_lock.acquire(self.name))

    def test_distinct_names_do_not_collide(self):
        other = f"Local\\PasswordVault-test-{uuid.uuid4().hex}"
        self.assertTrue(instance_lock.acquire(self.name))
        self.assertTrue(instance_lock.acquire(other))

    def test_focus_existing_is_safe_when_nothing_matches(self):
        # Must never raise: it runs on the failure path of startup.
        instance_lock.focus_existing(f"no-such-window-{uuid.uuid4().hex}")


if __name__ == "__main__":
    unittest.main()
