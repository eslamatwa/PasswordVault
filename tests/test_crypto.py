"""Unit tests for password_vault.crypto."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = Fernet is not None
except BaseException:  # noqa: BLE001 - cryptography may panic via pyo3
    _HAS_CRYPTO = False


@unittest.skipUnless(_HAS_CRYPTO, "cryptography library not available")
class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env_patcher = mock.patch.dict(
            os.environ, {"APPDATA": self.tmp})
        self.env_patcher.start()
        # Re-import with patched APPDATA so DATA_DIR points to tmp
        for mod in ("password_vault.settings",
                    "password_vault.crypto",
                    "password_vault"):
            import sys as _sys
            _sys.modules.pop(mod, None)
        from password_vault import crypto
        self.crypto = crypto

    def tearDown(self):
        self.env_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_salt_creation_and_persistence(self):
        salt1 = self.crypto.get_or_create_salt()
        self.assertEqual(len(salt1), 32)
        salt2 = self.crypto.get_or_create_salt()
        self.assertEqual(salt1, salt2, "salt should persist across calls")

    def test_read_salt_missing_returns_none(self):
        self.assertIsNone(self.crypto.read_salt())

    def test_read_salt_matches_stored_value(self):
        salt = self.crypto.get_or_create_salt()
        self.assertEqual(self.crypto.read_salt(), salt)

    def test_rotate_salt_can_be_undone_with_read_salt(self):
        original = self.crypto.get_or_create_salt()
        previous = self.crypto.read_salt()
        self.crypto.rotate_salt(b"\x09" * 32)
        self.assertNotEqual(self.crypto.read_salt(), original)
        self.crypto.rotate_salt(previous)
        self.assertEqual(self.crypto.read_salt(), original)

    def test_derive_key_deterministic(self):
        salt = b"\x00" * 32
        k1 = self.crypto.derive_key("hunter2", salt)
        k2 = self.crypto.derive_key("hunter2", salt)
        self.assertEqual(k1, k2)
        k3 = self.crypto.derive_key("hunter3", salt)
        self.assertNotEqual(k1, k3)

    def test_encrypt_decrypt_roundtrip(self):
        salt = b"\x01" * 32
        key = self.crypto.derive_key("pw", salt)
        data = {"entries": [{"title": "x", "password": "p"}],
                "categories": ["A"], "trash": []}
        token = self.crypto.encrypt_data(data, key)
        out = self.crypto.decrypt_data(token, key)
        self.assertEqual(out, data)

    def test_decrypt_with_wrong_key_fails(self):
        from cryptography.fernet import InvalidToken
        salt = b"\x02" * 32
        k1 = self.crypto.derive_key("a", salt)
        k2 = self.crypto.derive_key("b", salt)
        token = self.crypto.encrypt_data({"x": 1}, k1)
        with self.assertRaises(InvalidToken):
            self.crypto.decrypt_data(token, k2)

    def test_save_load_roundtrip_with_schema_migration(self):
        salt = self.crypto.get_or_create_salt()
        key = self.crypto.derive_key("pw", salt)
        # Write a "legacy" entry without id/created_at
        legacy = {"categories": ["General"],
                  "entries": [{"title": "old", "password": "x"}]}
        self.crypto.save_data(legacy, key)
        loaded = self.crypto.load_data(key)
        self.assertIn("id", loaded["entries"][0])
        self.assertIn("created_at", loaded["entries"][0])
        self.assertIn("modified_at", loaded["entries"][0])
        self.assertIn("trash", loaded)
        # Pre-migration backup should exist
        self.assertTrue(
            os.path.exists(self.crypto.DATA_FILE + ".pre-migration.bak"))

    def test_missing_vault_returns_a_default_structure(self):
        key = self.crypto.derive_key("pw", b"\x03" * 32)
        data = self.crypto.load_data(key)
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["trash"], [])
        self.assertIn("General", data["categories"])

    def test_oversized_vault_is_refused_before_decrypting(self):
        key = self.crypto.derive_key("pw", self.crypto.get_or_create_salt())
        self.crypto.save_data({"entries": [], "trash": [],
                               "categories": ["General"]}, key)
        with mock.patch.object(
                self.crypto.os.path, "getsize",
                return_value=self.crypto.MAX_VAULT_BYTES + 1):
            with self.assertRaises(ValueError):
                self.crypto.load_data(key)

    def test_expired_trash_is_dropped_and_recent_trash_is_kept(self):
        import datetime
        from password_vault.settings import TRASH_DAYS
        key = self.crypto.derive_key("pw", self.crypto.get_or_create_salt())
        now = datetime.datetime.now()
        old = (now - datetime.timedelta(days=TRASH_DAYS + 1)).isoformat()
        recent = (now - datetime.timedelta(days=1)).isoformat()
        self.crypto.save_data(
            {"categories": ["General"], "entries": [],
             "trash": [{"id": "old", "deleted_at": old},
                       {"id": "recent", "deleted_at": recent}]}, key)

        loaded = self.crypto.load_data(key)

        self.assertEqual([t["id"] for t in loaded["trash"]], ["recent"])

    def _seed_trash(self, items):
        key = self.crypto.derive_key("pw", self.crypto.get_or_create_salt())
        self.crypto.save_data(
            {"categories": ["General"], "entries": [], "trash": items}, key)
        return key

    def test_an_expired_item_is_purged_from_the_file_not_just_memory(self):
        """A retention period the file does not honour is not a retention
        period. The entry used to be filtered in memory and left in the
        ciphertext until the user happened to save."""
        import datetime
        from password_vault.settings import TRASH_DAYS
        old = (datetime.datetime.now()
               - datetime.timedelta(days=TRASH_DAYS + 1)).isoformat()
        key = self._seed_trash([{"id": "old", "deleted_at": old}])

        self.crypto.load_data(key)

        # Read again: the purge has to be on disk, not only in the copy
        # the first load returned.
        self.assertEqual(self.crypto.load_data(key)["trash"], [])

    def test_a_load_that_purges_nothing_does_not_rewrite_the_file(self):
        """The original reason for filtering in memory still holds: an
        ordinary startup must not re-encrypt the whole vault."""
        import datetime
        recent = (datetime.datetime.now()
                  - datetime.timedelta(days=1)).isoformat()
        key = self._seed_trash([{"id": "recent", "deleted_at": recent}])
        before = os.path.getmtime(self.crypto.DATA_FILE)

        self.crypto.load_data(key)

        self.assertEqual(os.path.getmtime(self.crypto.DATA_FILE), before)

    def test_an_empty_bin_does_not_rewrite_the_file(self):
        key = self._seed_trash([])
        before = os.path.getmtime(self.crypto.DATA_FILE)
        self.crypto.load_data(key)
        self.assertEqual(os.path.getmtime(self.crypto.DATA_FILE), before)

    def test_a_failed_purge_still_opens_the_vault(self):
        """Housekeeping must not stop a read-only disk from unlocking."""
        import datetime
        from password_vault.settings import TRASH_DAYS
        old = (datetime.datetime.now()
               - datetime.timedelta(days=TRASH_DAYS + 1)).isoformat()
        key = self._seed_trash([{"id": "old", "deleted_at": old},
                                {"id": "keep", "deleted_at":
                                 datetime.datetime.now().isoformat()}])

        with mock.patch.object(self.crypto, "save_data",
                               side_effect=OSError("read-only")):
            loaded = self.crypto.load_data(key)

        self.assertEqual([t["id"] for t in loaded["trash"]], ["keep"])


class PasswordStrengthTests(unittest.TestCase):
    def test_empty_string(self):
        from password_vault.security import password_strength
        score, label, _ = password_strength("")
        self.assertEqual(score, 0)
        self.assertEqual(label, "")

    def test_monotonic_in_length(self):
        from password_vault.security import password_strength
        scores = [password_strength("Aa1!" * i)[0] for i in range(1, 6)]
        # Each step should be >= previous (no regressions)
        for a, b in zip(scores, scores[1:]):
            self.assertLessEqual(a, b, f"score regressed: {scores}")

    def test_strong_password(self):
        from password_vault.security import password_strength
        score, label, _ = password_strength("Aa1!Bb2@Cc3#Dd4$")
        self.assertEqual(score, 4)
        self.assertEqual(label, "Very Strong")

    def test_weak_password(self):
        from password_vault.security import password_strength
        score, _, _ = password_strength("abc")
        self.assertEqual(score, 0)


class GeneratePasswordTests(unittest.TestCase):
    def test_default_length(self):
        from password_vault.security import generate_password
        pw = generate_password(16)
        self.assertEqual(len(pw), 16)

    def test_short_length_still_satisfies_required(self):
        from password_vault.security import generate_password
        # Length 4 with all classes — should still produce 4 chars
        pw = generate_password(4, True, True, True, True)
        self.assertEqual(len(pw), 4)

    def test_only_digits(self):
        from password_vault.security import generate_password
        pw = generate_password(20, upper=False, lower=False,
                                digits=True, symbols=False)
        self.assertTrue(all(c.isdigit() for c in pw),
                         f"unexpected chars in {pw}")

    def test_no_classes_falls_back(self):
        from password_vault.security import generate_password
        pw = generate_password(10, False, False, False, False)
        self.assertEqual(len(pw), 10)


@unittest.skipUnless(_HAS_CRYPTO, "cryptography library not available")
class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip(self):
        from password_vault.crypto import (
            export_encrypted_backup, import_encrypted_backup,
        )
        data = {"entries": [{"title": "x", "password": "p"}],
                "categories": ["A"], "trash": []}
        path = os.path.join(self.tmp, "vault-backup.pvbak")
        export_encrypted_backup(data, "correcthorse", path)
        out = import_encrypted_backup(path, "correcthorse")
        self.assertEqual(out, data)

    def test_wrong_password_fails(self):
        from password_vault.crypto import (
            export_encrypted_backup, import_encrypted_backup,
        )
        data = {"entries": [], "categories": [], "trash": []}
        path = os.path.join(self.tmp, "vault-backup.pvbak")
        export_encrypted_backup(data, "right", path)
        with self.assertRaises(ValueError):
            import_encrypted_backup(path, "wrong")

    def test_backup_carries_own_salt(self):
        """Two backups of the same data with the same password should
        differ — fresh salt each time."""
        from password_vault.crypto import export_encrypted_backup
        data = {"entries": [], "categories": [], "trash": []}
        a = os.path.join(self.tmp, "a.pvbak")
        b = os.path.join(self.tmp, "b.pvbak")
        export_encrypted_backup(data, "pw", a)
        export_encrypted_backup(data, "pw", b)
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertNotEqual(fa.read(), fb.read())

    def test_malformed_file_rejected(self):
        from password_vault.crypto import import_encrypted_backup
        path = os.path.join(self.tmp, "junk.pvbak")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json")
        with self.assertRaises(ValueError):
            import_encrypted_backup(path, "pw")

    def test_wrong_format_rejected(self):
        import json
        from password_vault.crypto import import_encrypted_backup
        path = os.path.join(self.tmp, "wrong.pvbak")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "Other-App", "version": 1}, f)
        with self.assertRaises(ValueError):
            import_encrypted_backup(path, "pw")

    def test_empty_password_rejected_on_export(self):
        from password_vault.crypto import export_encrypted_backup
        path = os.path.join(self.tmp, "x.pvbak")
        with self.assertRaises(ValueError):
            export_encrypted_backup({"entries": []}, "", path)


class HostExtractTests(unittest.TestCase):
    def test_url_parsing_handles_user_at_host(self):
        # Functional smoke: ssh://user@host:2222/path → host
        import urllib.parse
        parts = urllib.parse.urlsplit("ssh://user@example.com:2222/path")
        self.assertEqual(parts.hostname, "example.com")
        self.assertEqual(parts.port, 2222)


if __name__ == "__main__":
    unittest.main()
