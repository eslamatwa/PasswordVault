"""Unit tests for settings loading and validation."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock


class LoadSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.tmp})
        self.env.start()
        import sys
        for mod in ("password_vault.settings", "password_vault"):
            sys.modules.pop(mod, None)
        from password_vault import settings
        self.settings = settings

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, payload):
        with open(self.settings.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_defaults_when_no_file(self):
        self.assertEqual(self.settings.load_settings(),
                         self.settings.DEFAULT_SETTINGS)

    def test_valid_values_are_kept(self):
        self._write({"auto_lock_minutes": 15, "theme": "Light",
                     "start_minimized": True})
        loaded = self.settings.load_settings()
        self.assertEqual(loaded["auto_lock_minutes"], 15)
        self.assertEqual(loaded["theme"], "Light")
        self.assertTrue(loaded["start_minimized"])

    def test_wrong_type_falls_back_to_default(self):
        self._write({"auto_lock_minutes": "soon"})
        loaded = self.settings.load_settings()
        self.assertEqual(
            loaded["auto_lock_minutes"],
            self.settings.DEFAULT_SETTINGS["auto_lock_minutes"])

    def test_bool_is_not_accepted_as_a_duration(self):
        self._write({"auto_lock_minutes": True})
        self.assertEqual(
            self.settings.load_settings()["auto_lock_minutes"],
            self.settings.DEFAULT_SETTINGS["auto_lock_minutes"])

    def test_out_of_range_is_rejected(self):
        self._write({"auto_lock_minutes": -5, "gen_length": 9999,
                     "clipboard_clear_seconds": 10 ** 9})
        loaded = self.settings.load_settings()
        d = self.settings.DEFAULT_SETTINGS
        self.assertEqual(loaded["auto_lock_minutes"], d["auto_lock_minutes"])
        self.assertEqual(loaded["gen_length"], d["gen_length"])
        self.assertEqual(loaded["clipboard_clear_seconds"],
                         d["clipboard_clear_seconds"])

    def test_unknown_theme_is_rejected(self):
        self._write({"theme": "Neon"})
        self.assertEqual(self.settings.load_settings()["theme"],
                         self.settings.DEFAULT_SETTINGS["theme"])

    def test_unknown_keys_are_dropped(self):
        self._write({"evil": {"nested": True}, "gen_length": 20})
        loaded = self.settings.load_settings()
        self.assertNotIn("evil", loaded)
        self.assertEqual(loaded["gen_length"], 20)

    def test_non_object_file_falls_back_to_defaults(self):
        with open(self.settings.SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("[1, 2, 3]")
        self.assertEqual(self.settings.load_settings(),
                         self.settings.DEFAULT_SETTINGS)

    def test_corrupt_file_falls_back_to_defaults(self):
        with open(self.settings.SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(self.settings.load_settings(),
                         self.settings.DEFAULT_SETTINGS)

    def test_save_then_load_roundtrip(self):
        s = dict(self.settings.DEFAULT_SETTINGS)
        s["theme"] = "Light"
        s["auto_lock_minutes"] = 30
        self.settings.save_settings(s)
        self.assertEqual(self.settings.load_settings(), s)

    def test_every_default_passes_its_own_validation(self):
        self._write(dict(self.settings.DEFAULT_SETTINGS))
        self.assertEqual(self.settings.load_settings(),
                         self.settings.DEFAULT_SETTINGS)

    def test_lockout_state_survives_a_reload(self):
        # The streak and the deadline are what stop a restart from handing
        # an attacker a fresh set of attempts, so they have to round-trip.
        self._write({"failed_streak": 12, "lockout_until": 1893456000})
        loaded = self.settings.load_settings()
        self.assertEqual(loaded["failed_streak"], 12)
        self.assertEqual(loaded["lockout_until"], 1893456000)

    def test_negative_lockout_state_falls_back_to_default(self):
        self._write({"failed_streak": -1, "lockout_until": -5})
        loaded = self.settings.load_settings()
        self.assertEqual(loaded["failed_streak"], 0)
        self.assertEqual(loaded["lockout_until"], 0)

    def test_non_integer_lockout_state_falls_back_to_default(self):
        self._write({"failed_streak": "many", "lockout_until": True})
        loaded = self.settings.load_settings()
        self.assertEqual(loaded["failed_streak"], 0)
        self.assertEqual(loaded["lockout_until"], 0)


if __name__ == "__main__":
    unittest.main()
