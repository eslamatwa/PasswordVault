"""Restore-path tests: a failed write must leave the vault openable.

The restore helpers swap ``app.data``/``app.key`` and rotate the salt. If
the vault write fails midway, the salt on disk must still match the
ciphertext, otherwise no password can open the vault again.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

try:
    import customtkinter
    from cryptography.fernet import Fernet
    _AVAILABLE = customtkinter is not None and Fernet is not None
except BaseException:  # noqa: BLE001 - tkinter/cryptography may fail hard
    _AVAILABLE = False

_RELOADED = ("password_vault.ui.dialogs.backup",
             "password_vault.ui.dialogs",
             "password_vault.ui",
             "password_vault.crypto",
             "password_vault.settings",
             "password_vault")


class _FakeDialog:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class _FakeApp:
    def __init__(self, data=None, key=None):
        self.data = data
        self.key = key
        self.refreshed = False
        self.unlocked = False

    def refresh_categories(self):
        self.refreshed = True

    def refresh_entries(self):
        self.refreshed = True

    def _finish_unlock_after_restore(self):
        self.unlocked = True


@unittest.skipUnless(_AVAILABLE, "customtkinter/cryptography not available")
class RestoreIntoUnlockedVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.tmp})
        self.env.start()
        for mod in _RELOADED:
            sys.modules.pop(mod, None)
        from password_vault import crypto
        from password_vault.ui.dialogs import backup
        self.crypto = crypto
        self.backup = backup
        self.key = crypto.derive_key("pw", crypto.get_or_create_salt())

    def tearDown(self):
        self.env.stop()
        for mod in _RELOADED:
            sys.modules.pop(mod, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_successful_restore_replaces_the_live_vault(self):
        app = _FakeApp({"entries": [{"title": "old"}]}, self.key)
        dlg = _FakeDialog()
        new = {"entries": [{"title": "new"}], "categories": ["A"],
               "trash": []}

        self.backup._restore_into_unlocked_vault(app, new, dlg, None)

        self.assertEqual(app.data, new)
        self.assertTrue(dlg.destroyed)
        self.assertEqual(
            self.crypto.load_data(self.key)["entries"][0]["title"], "new")

    def test_failed_write_keeps_the_live_vault_in_memory(self):
        original = {"entries": [{"title": "old"}]}
        app = _FakeApp(original, self.key)
        dlg = _FakeDialog()

        with mock.patch.object(self.backup, "save_data",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.backup._restore_into_unlocked_vault(
                    app, {"entries": [{"title": "new"}]}, dlg, None)

        self.assertIs(app.data, original)
        self.assertFalse(dlg.destroyed)


@unittest.skipUnless(_AVAILABLE, "customtkinter/cryptography not available")
class RestoreToNewVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.tmp})
        self.env.start()
        for mod in _RELOADED:
            sys.modules.pop(mod, None)
        from password_vault import crypto
        from password_vault.ui.dialogs import backup
        self.crypto = crypto
        self.backup = backup

    def tearDown(self):
        self.env.stop()
        for mod in _RELOADED:
            sys.modules.pop(mod, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_opens_with_the_new_master_password(self):
        app = _FakeApp()
        dlg = _FakeDialog()
        data = {"entries": [{"title": "from backup"}], "categories": ["A"],
                "trash": []}

        self.backup._restore_to_new_vault(app, data, dlg, "NewMaster123")

        self.assertTrue(dlg.destroyed)
        self.assertTrue(app.unlocked)
        key = self.crypto.derive_key("NewMaster123",
                                      self.crypto.read_salt())
        self.assertEqual(
            self.crypto.load_data(key)["entries"][0]["title"], "from backup")

    def test_failed_write_puts_the_previous_salt_back(self):
        old_salt = self.crypto.get_or_create_salt()
        old_key = self.crypto.derive_key("OldMaster123", old_salt)
        self.crypto.save_data({"entries": [{"title": "old"}],
                               "categories": ["A"], "trash": []}, old_key)
        app = _FakeApp()
        dlg = _FakeDialog()

        with mock.patch.object(self.backup, "save_data",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.backup._restore_to_new_vault(
                    app, {"entries": []}, dlg, "NewMaster123")

        self.assertEqual(self.crypto.read_salt(), old_salt)
        self.assertEqual(
            self.crypto.load_data(old_key)["entries"][0]["title"], "old")
        self.assertFalse(dlg.destroyed)

    def test_failed_write_on_a_fresh_install_leaves_no_salt(self):
        app = _FakeApp()
        dlg = _FakeDialog()

        with mock.patch.object(self.backup, "save_data",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.backup._restore_to_new_vault(
                    app, {"entries": []}, dlg, "NewMaster123")

        self.assertIsNone(self.crypto.read_salt())


if __name__ == "__main__":
    unittest.main()
