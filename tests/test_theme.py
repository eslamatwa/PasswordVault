"""Unit tests for the dual-mode theme palette."""

from __future__ import annotations

import unittest

import customtkinter as ctk

from password_vault import theme


class PaletteTests(unittest.TestCase):
    def tearDown(self):
        ctk.set_appearance_mode("Dark")

    def test_every_color_token_is_a_light_dark_pair(self):
        skip = {"CAT_EMOJIS", "CARD_COLORS", "DEFAULT_EMOJI", "Color"}
        checked = 0
        for name, value in vars(theme).items():
            if name.startswith("_") or name in skip or name.islower():
                continue
            if not isinstance(value, tuple):
                continue
            self.assertEqual(len(value), 2, name)
            for element in value:
                self.assertIsInstance(element, str, name)
                self.assertTrue(element.startswith("#"), f"{name}={element}")
            checked += 1
        self.assertGreater(checked, 20, "palette looks empty")

    def test_card_presets_have_both_modes(self):
        for key, info in theme.CARD_COLORS.items():
            self.assertEqual(len(info["bg"]), 2, key)
            self.assertIn("label", info)

    def test_resolve_follows_the_appearance_mode(self):
        ctk.set_appearance_mode("Dark")
        self.assertEqual(theme.resolve(theme.BG), theme.BG[1])
        ctk.set_appearance_mode("Light")
        self.assertEqual(theme.resolve(theme.BG), theme.BG[0])

    def test_resolve_passes_plain_strings_through(self):
        self.assertEqual(theme.resolve("#123456"), "#123456")
        self.assertIsNone(theme.resolve(None))

    def test_menu_style_is_all_single_colors(self):
        for mode in ("Light", "Dark"):
            ctk.set_appearance_mode(mode)
            style = theme.menu_style()
            for key in ("bg", "fg", "activebackground", "activeforeground"):
                self.assertIsInstance(style[key], str, f"{mode}/{key}")
                self.assertTrue(style[key].startswith("#"))

    def test_cat_emoji_falls_back(self):
        self.assertEqual(theme.cat_emoji("Banking"), "🏦")
        self.assertEqual(theme.cat_emoji("Nope"), theme.DEFAULT_EMOJI)


if __name__ == "__main__":
    unittest.main()
