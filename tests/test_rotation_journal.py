"""Recovery from an interrupted master-password change.

Changing the master password writes the vault under the new key and then
rotates the salt. Between those two writes the ciphertext and the salt
disagree, and if the rotation failed *and* the rollback re-save also failed,
nothing on disk said which key the file was under — the vault could not be
opened by any password.

The journal records the target salt before the re-encryption starts, so the
login screen can try both. These tests reconstruct each way the change can
be interrupted and assert the vault still opens afterwards.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = Fernet is not None
except BaseException:  # noqa: BLE001 - cryptography may panic via pyo3
    _HAS_CRYPTO = False

VAULT = {"categories": ["General"], "entries": [
    {"id": "1", "title": "Bank", "password": "s3cret"}], "trash": []}


@unittest.skipUnless(_HAS_CRYPTO, "cryptography library not available")
class RotationJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.tmp})
        self.env.start()
        for mod in ("password_vault.crypto", "password_vault.settings",
                    "password_vault"):
            sys.modules.pop(mod, None)
        from password_vault import crypto
        self.crypto = crypto

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_vault(self, password="OldMaster123"):
        salt = self.crypto.get_or_create_salt()
        key = self.crypto.derive_key(password, salt)
        self.crypto.save_data(VAULT, key)
        return salt, key

    def _open_with(self, password):
        """Try every candidate salt, the way the login screen does."""
        from cryptography.fernet import InvalidToken
        for salt in self.crypto.candidate_salts():
            try:
                return self.crypto.load_data(
                    self.crypto.derive_key(password, salt))
            except InvalidToken:
                continue
        return None

    # ── the journal itself ──
    def test_no_journal_means_one_candidate(self):
        self._make_vault()
        self.assertEqual(len(self.crypto.candidate_salts()), 1)

    def test_a_journal_adds_the_pending_salt(self):
        self._make_vault()
        pending = os.urandom(32)
        self.crypto.begin_rotation(pending)
        salts = self.crypto.candidate_salts()
        self.assertEqual(len(salts), 2)
        self.assertIn(pending, salts)

    def test_ending_a_rotation_removes_the_journal(self):
        self._make_vault()
        self.crypto.begin_rotation(os.urandom(32))
        self.crypto.end_rotation()
        self.assertEqual(len(self.crypto.candidate_salts()), 1)

    def test_ending_a_rotation_that_never_began_is_harmless(self):
        self._make_vault()
        self.crypto.end_rotation()  # must not raise
        self.assertEqual(len(self.crypto.candidate_salts()), 1)

    def test_a_journal_matching_the_live_salt_is_not_duplicated(self):
        salt, _ = self._make_vault()
        self.crypto.begin_rotation(salt)
        self.assertEqual(self.crypto.candidate_salts(), [salt])

    # ── the interruption cases ──
    def test_interrupted_before_the_vault_was_written(self):
        """Journal exists, vault still under the old key. Old password."""
        self._make_vault()
        self.crypto.begin_rotation(os.urandom(32))

        self.assertIsNotNone(self._open_with("OldMaster123"))
        self.assertIsNone(self._open_with("NewMaster123"))

    def test_interrupted_after_the_vault_was_written(self):
        """The case that used to be unrecoverable.

        The vault is under the new key, the salt file still holds the old
        one, and the rollback never landed. Without the journal nothing on
        disk points at the new salt and no password opens the file.
        """
        self._make_vault()
        new_salt = os.urandom(32)
        self.crypto.begin_rotation(new_salt)
        self.crypto.save_data(
            VAULT, self.crypto.derive_key("NewMaster123", new_salt))
        # rotate_salt never ran, and neither did the rollback.

        recovered = self._open_with("NewMaster123")
        self.assertIsNotNone(recovered, "the vault was unrecoverable")
        self.assertEqual(recovered["entries"][0]["title"], "Bank")

    def test_a_completed_rotation_opens_with_the_new_password_only(self):
        self._make_vault()
        new_salt = os.urandom(32)
        self.crypto.begin_rotation(new_salt)
        self.crypto.save_data(
            VAULT, self.crypto.derive_key("NewMaster123", new_salt))
        self.crypto.rotate_salt(new_salt)
        self.crypto.end_rotation()

        self.assertIsNotNone(self._open_with("NewMaster123"))
        self.assertIsNone(self._open_with("OldMaster123"))
        self.assertEqual(len(self.crypto.candidate_salts()), 1)

    def test_a_stale_journal_does_not_open_the_vault_to_a_wrong_password(self):
        """Recovery must widen which *salt* is tried, never which password."""
        self._make_vault()
        self.crypto.begin_rotation(os.urandom(32))
        self.assertIsNone(self._open_with("NotTheMasterPassword"))

    def test_the_journal_file_is_permission_restricted(self):
        self._make_vault()
        self.crypto.begin_rotation(os.urandom(32))
        self.assertTrue(os.path.exists(self.crypto.ROTATION_FILE))
        if sys.platform != "win32":
            mode = os.stat(self.crypto.ROTATION_FILE).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_an_unreadable_journal_is_ignored(self):
        salt, _ = self._make_vault()
        with mock.patch.object(self.crypto, "ROTATION_FILE",
                               os.path.join(self.tmp, "nope", "x")):
            self.assertEqual(self.crypto.candidate_salts(), [salt])

    def test_an_empty_journal_is_ignored(self):
        salt, _ = self._make_vault()
        with open(self.crypto.ROTATION_FILE, "wb") as f:
            f.write(b"")
        self.assertEqual(self.crypto.candidate_salts(), [salt])


if __name__ == "__main__":
    unittest.main()
