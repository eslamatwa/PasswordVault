"""Unit tests for password_vault.crypto."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

try:
    from cryptography.fernet import Fernet  # noqa: F401
    _HAS_CRYPTO = True
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
