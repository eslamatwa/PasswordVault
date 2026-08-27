"""Tests for the portable encrypted backup format.

A backup carries its own salt and KDF parameters so it can be restored on a
clean machine. Every rejection path has to fail closed, and a wrong password
must be indistinguishable from a tampered file.
"""

from __future__ import annotations

import json
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

VAULT = {"categories": ["General", "Work"],
         "entries": [{"id": "1", "title": "Bank", "username": "u",
                      "password": "s3cret", "notes": "بالعربي"}],
         "trash": []}


@unittest.skipUnless(_HAS_CRYPTO, "cryptography library not available")
class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.tmp})
        self.env.start()
        for mod in ("password_vault.crypto", "password_vault.settings",
                    "password_vault"):
            sys.modules.pop(mod, None)
        from password_vault import crypto
        self.crypto = crypto
        self.path = os.path.join(self.tmp, "vault.pvbak")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, password="BackupPass123"):
        self.crypto.export_encrypted_backup(VAULT, password, self.path)

    def _payload(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _rewrite(self, payload):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_roundtrip_preserves_the_vault(self):
        self._write()
        out = self.crypto.import_encrypted_backup(self.path, "BackupPass123")
        self.assertEqual(out, VAULT)

    def test_backup_is_independent_of_the_vault_salt(self):
        self._write()
        payload = self._payload()
        self.assertNotEqual(payload["salt"],
                            self.crypto.get_or_create_salt())
        self.crypto.rotate_salt()
        # Rotating the live salt must not affect an existing backup.
        self.assertEqual(
            self.crypto.import_encrypted_backup(self.path, "BackupPass123"),
            VAULT)

    def test_password_is_required(self):
        with self.assertRaises(ValueError):
            self.crypto.export_encrypted_backup(VAULT, "", self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_no_plaintext_leaks_into_the_file(self):
        self._write()
        with open(self.path, "rb") as f:
            raw = f.read()
        for secret in (b"s3cret", b"Bank", b"BackupPass123"):
            self.assertNotIn(secret, raw)

    def test_wrong_password_is_rejected(self):
        self._write()
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "WrongPass123")

    def test_tampered_ciphertext_reports_the_same_error_as_a_wrong_password(
            self):
        self._write()
        payload = self._payload()
        token = payload["ciphertext"]
        flipped = "A" if token[40] != "A" else "B"
        payload["ciphertext"] = token[:40] + flipped + token[41:]
        self._rewrite(payload)
        with self.assertRaises(ValueError) as tampered:
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

        self._write()
        with self.assertRaises(ValueError) as wrong_password:
            self.crypto.import_encrypted_backup(self.path, "WrongPass123")

        self.assertEqual(str(tampered.exception),
                         str(wrong_password.exception))

    def test_foreign_json_is_rejected(self):
        self._rewrite({"hello": "world"})
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_not_json_is_rejected(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("this is not json")
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_future_version_is_rejected(self):
        self._write()
        payload = self._payload()
        payload["version"] = self.crypto.BACKUP_VERSION + 1
        self._rewrite(payload)
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_unknown_kdf_is_rejected(self):
        self._write()
        payload = self._payload()
        payload["kdf"] = "md5"
        self._rewrite(payload)
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_missing_field_is_rejected(self):
        self._write()
        payload = self._payload()
        del payload["salt"]
        self._rewrite(payload)
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_oversized_file_is_refused_before_reading(self):
        self._write()
        with mock.patch.object(self.crypto.os.path, "getsize",
                               return_value=self.crypto.MAX_VAULT_BYTES + 1):
            with self.assertRaises(ValueError):
                self.crypto.import_encrypted_backup(
                    self.path, "BackupPass123")

    def test_failed_write_leaves_no_partial_file(self):
        with mock.patch.object(self.crypto.json, "dump",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.crypto.export_encrypted_backup(
                    VAULT, "BackupPass123", self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_existing_backup_survives_a_failed_overwrite(self):
        self._write()
        with mock.patch.object(self.crypto.json, "dump",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.crypto.export_encrypted_backup(
                    {"entries": []}, "Other123", self.path)
        self.assertEqual(
            self.crypto.import_encrypted_backup(self.path, "BackupPass123"),
            VAULT)

    def test_backup_of_the_wrong_shape_is_refused(self):
        # A hand-edited backup decrypts cleanly and is still not a vault.
        # Restoring used to assign it onto the live vault and only fail
        # later in the UI — after the file was written and, at login,
        # after the salt had been rotated.
        self.crypto.export_encrypted_backup(
            ["not", "a", "vault"], "BackupPass123", self.path)
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_backup_with_a_malformed_entry_list_is_refused(self):
        self.crypto.export_encrypted_backup(
            {"entries": ["just a string"]}, "BackupPass123", self.path)
        with self.assertRaises(ValueError):
            self.crypto.import_encrypted_backup(self.path, "BackupPass123")

    def test_backup_missing_containers_is_filled_in(self):
        self.crypto.export_encrypted_backup(
            {"entries": [{"title": "a"}]}, "BackupPass123", self.path)
        out = self.crypto.import_encrypted_backup(self.path, "BackupPass123")
        self.assertEqual(out["entries"], [{"title": "a"}])
        self.assertEqual(out["trash"], [])
        self.assertEqual(out["categories"], self.crypto.DEFAULT_CATEGORIES)


@unittest.skipUnless(_HAS_CRYPTO, "cryptography library not available")
class NormalizeVaultTests(unittest.TestCase):
    """The shape guard restores run through before touching the vault."""

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

    def test_a_complete_vault_passes_through_unchanged(self):
        self.assertEqual(self.crypto.normalize_vault(VAULT), VAULT)

    def test_unknown_keys_are_preserved(self):
        # Forward compatibility: a newer version's field must survive a
        # round-trip through an older one rather than being dropped.
        data = dict(VAULT, future_field={"x": 1})
        self.assertEqual(
            self.crypto.normalize_vault(data)["future_field"], {"x": 1})

    def test_the_input_is_not_mutated(self):
        data = {"entries": []}
        self.crypto.normalize_vault(data)
        self.assertNotIn("trash", data)

    def test_non_dict_is_refused(self):
        for bad in ([], "vault", 7, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.crypto.normalize_vault(bad)

    def test_non_dict_entries_are_refused(self):
        for bad in ({"entries": "nope"}, {"entries": [1, 2]},
                    {"entries": [{"ok": True}, "no"]}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.crypto.normalize_vault(bad)

    def test_bad_categories_fall_back_to_the_defaults(self):
        for bad in ("General", [1, 2], None):
            with self.subTest(bad=bad):
                out = self.crypto.normalize_vault(
                    {"entries": [], "categories": bad})
                self.assertEqual(out["categories"],
                                 self.crypto.DEFAULT_CATEGORIES)

    def test_bad_trash_falls_back_to_empty(self):
        out = self.crypto.normalize_vault({"entries": [], "trash": "gone"})
        self.assertEqual(out["trash"], [])


if __name__ == "__main__":
    unittest.main()
