"""Every user-facing string reaches the translator.

This is the gate that keeps the extraction honest. A string added later in
a plain ``text="..."`` is invisible in English — it simply keeps working —
and only shows up as a stray Latin phrase in the middle of an Arabic
screen. Static analysis catches it at commit time instead.

The rule: any string literal passed to a UI text keyword, or as the message
argument of ``tip()``, must be inside a ``t(...)`` call. Decoration is
exempt — emoji, separators, masks and format specs carry no language.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent

UI_KWARGS = {"text", "placeholder_text", "label"}

UI_FILES = [
    REPO / "main.py",
    # security.py renders the strength and age labels, so it holds
    # user-facing text even though it is not a UI module.
    REPO / "password_vault" / "security.py",
    REPO / "password_vault" / "ui" / "widgets.py",
    REPO / "password_vault" / "ui" / "floating.py",
    REPO / "password_vault" / "ui" / "mini_vault.py",
] + sorted((REPO / "password_vault" / "ui" / "dialogs").glob("*.py"))

# Strings that are deliberately not translated, with the reason.
EXEMPT = {
    # Widget geometry and state, not language.
    "", " ", "\n",
    # The password mask and the show/hide glyphs.
    "●", "👁", "🙈",
    # Font families and an example URL: not language.
    "Segoe UI", "Consolas", "https://example.com",
    # Product names stay as they are written, in every language. The CSV
    # profile labels reach the UI the same way, through Profile.label.
    "Bitwarden JSON", "1Password (.1pux)",
}


def is_decoration(s: str) -> bool:
    """True when the literal carries no words to translate."""
    if s in EXEMPT:
        return True
    if not s.strip():
        return True
    # Needs a run of two or more Latin letters to be a phrase.
    letters = 0
    for ch in s:
        if "a" <= ch.lower() <= "z":
            letters += 1
            if letters >= 2:
                return False
        else:
            letters = 0
    return True


def wrapped_in_t(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "t")


class Collector(ast.NodeVisitor):
    """Report bare literals in UI text positions."""

    def __init__(self, path):
        self.path = path
        self.bare: list[tuple[int, str]] = []

    def _check(self, node, where):
        """Recurse through the shapes a UI text argument can take."""
        if wrapped_in_t(node):
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not is_decoration(node.value):
                self.bare.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            # f-string: any literal part with words needs translating.
            for part in node.values:
                if isinstance(part, ast.Constant) and \
                        isinstance(part.value, str) and \
                        not is_decoration(part.value):
                    self.bare.append((node.lineno, part.value))
        elif isinstance(node, ast.IfExp):
            # text=("A" if cond else "B") — both arms are UI strings.
            self._check(node.body, where)
            self._check(node.orelse, where)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            self._check(node.left, where)
            self._check(node.right, where)

    def visit_Call(self, node):
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "tip" and len(node.args) >= 2:
            self._check(node.args[1], "tip")
        for kw in node.keywords:
            if kw.arg in UI_KWARGS:
                self._check(kw.value, kw.arg)
        self.generic_visit(node)


class TranslationCoverageTests(unittest.TestCase):
    def test_no_bare_user_facing_strings(self):
        problems = []
        for path in UI_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            c = Collector(path)
            c.visit(tree)
            for line, text in c.bare:
                rel = path.relative_to(REPO)
                problems.append(f"{rel}:{line}: {text!r}")
        self.assertEqual(
            problems, [],
            "user-facing strings not wrapped in t():\n  "
            + "\n  ".join(problems))


class CatalogCoverageTests(unittest.TestCase):
    """Every string that reaches t() has an Arabic entry.

    A missing entry is not an error at runtime — t() returns the English —
    which is precisely why it needs a test: a half-translated screen looks
    like a rendering bug, not like a gap in a data file.

    Strings that reach t() indirectly, through a helper that translates its
    own arguments, are collected from those helpers' call sites too.
    """

    # helper name -> indices of positional args that are user-facing.
    # Indices are into ast `node.args`, which excludes `self` — so a method
    # called as `self._alert(title, message)` has its title at 0, not 1.
    HELPER_ARGS = {
        "dialog_header": (1,),
        "ios_group": (1,),
        "ios_field": (1,),
        "ios_combo": (1,),
        "stat_row": (2,),
        "info_row": (2,),
        "setting_row": (2,),
        "_make_dialog": (0,),
        "_confirm": (0, 1),
        "_alert": (0, 1),
    }
    HELPER_KWARGS = {"subtitle", "confirm_text", "placeholder",
                     "window_title", "message"}

    @staticmethod
    def _collect(node, found):
        """Add the literals a helper argument can carry.

        ``_make_dialog("Edit Password" if is_edit else "New Password", …)``
        is one argument holding two user-facing strings.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not is_decoration(node.value):
                found.add(node.value)
        elif isinstance(node, ast.IfExp):
            CatalogCoverageTests._collect(node.body, found)
            CatalogCoverageTests._collect(node.orelse, found)

    def _strings_reaching_t(self):
        found = set()

        for path in UI_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (getattr(node.func, "id", None)
                        or getattr(node.func, "attr", None))

                if name == "t" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and \
                            isinstance(arg.value, str):
                        found.add(arg.value)

                for idx in self.HELPER_ARGS.get(name, ()):
                    if idx < len(node.args):
                        self._collect(node.args[idx], found)
                if name in self.HELPER_ARGS:
                    for kw in node.keywords:
                        if kw.arg in self.HELPER_KWARGS:
                            self._collect(kw.value, found)

                # button_row takes its labels in dicts; the helper calls
                # t() on each one on the way through.
                if name == "button_row":
                    for spec in ast.walk(node):
                        if not isinstance(spec, ast.Dict):
                            continue
                        for key, value in zip(spec.keys, spec.values):
                            if isinstance(key, ast.Constant) and \
                                    key.value == "text":
                                self._collect(value, found)
        return found

    def test_every_string_is_translated_in_every_catalog(self):
        """Runs per catalog, so adding a language is a data change.

        A new entry in ``CATALOG`` is picked up here automatically and has
        to be complete on the same terms Arabic is.
        """
        from password_vault.i18n import CATALOG
        self.assertTrue(CATALOG, "no catalogs to check")
        used = self._strings_reaching_t()
        for language, table in CATALOG.items():
            with self.subTest(language=language):
                missing = sorted(used - set(table))
                self.assertEqual(
                    missing, [],
                    f"strings with no {language} entry:\n  "
                    + "\n  ".join(repr(m) for m in missing))

    def test_no_catalog_has_entries_nothing_uses(self):
        """A stale key is dead weight and hides a renamed string."""
        from password_vault.i18n import CATALOG
        used = self._strings_reaching_t()
        for language, table in CATALOG.items():
            with self.subTest(language=language):
                unused = sorted(set(table) - used)
                self.assertEqual(
                    unused, [],
                    f"{language} entries no call site uses:\n  "
                    + "\n  ".join(repr(u) for u in unused))

    def test_every_declared_language_has_a_catalog_or_is_the_source(self):
        """A language in the dropdown with no catalog would silently show
        English while claiming to be something else."""
        from password_vault.i18n import CATALOG, LANGUAGE_VALUES
        for value in LANGUAGE_VALUES:
            if value == "English":
                continue  # the source language needs no table
            with self.subTest(language=value):
                self.assertIn(value, CATALOG)

    def test_the_settings_codes_match_the_declared_languages(self):
        from password_vault.i18n import LANGUAGE_VALUES
        from password_vault.settings import LANGUAGE_CODES
        self.assertEqual(set(LANGUAGE_VALUES), set(LANGUAGE_CODES))


class CatalogTests(unittest.TestCase):
    def test_no_catalog_has_empty_translations(self):
        from password_vault.i18n import CATALOG
        for language, table in CATALOG.items():
            with self.subTest(language=language):
                empty = [k for k, v in table.items() if not v.strip()]
                self.assertEqual(empty, [])

    def test_no_catalog_entry_echoes_its_key(self):
        """An entry equal to its key is a placeholder someone forgot."""
        from password_vault.i18n import CATALOG
        for language, table in CATALOG.items():
            with self.subTest(language=language):
                echoes = [k for k, v in table.items() if k == v]
                self.assertEqual(echoes, [])

    def test_every_catalog_keeps_its_placeholders(self):
        """A translation may reorder placeholders but not invent or drop
        them; a mismatch raises inside whichever dialog uses the string."""
        import re
        from password_vault.i18n import CATALOG

        field = re.compile(r"\{(\w+)\}")
        for language, table in CATALOG.items():
            with self.subTest(language=language):
                bad = [source for source, translated in table.items()
                       if set(field.findall(source))
                       != set(field.findall(translated))]
                self.assertEqual(bad, [])

    def test_language_round_trips_through_its_label(self):
        from password_vault.i18n import (
            LANGUAGE_VALUES, label_for, value_for)
        for value in LANGUAGE_VALUES:
            self.assertEqual(value_for(label_for(value)), value)

    def test_unknown_language_falls_back_to_english(self):
        from password_vault import i18n
        try:
            i18n.set_language("Klingon")
            self.assertEqual(i18n.get_language(), "English")
            self.assertFalse(i18n.is_rtl())
        finally:
            i18n.set_language("English")

    def test_a_broken_translation_does_not_raise(self):
        """A bad placeholder falls back instead of taking a dialog down."""
        from password_vault import i18n
        original = dict(i18n.ARABIC)
        try:
            i18n.ARABIC["Open {url}"] = "افتح {nope}"
            i18n.set_language("Arabic")
            out = i18n.t("Open {url}", url="https://example.com")
            self.assertIn("https://example.com", out)
        finally:
            i18n.ARABIC.clear()
            i18n.ARABIC.update(original)
            i18n.set_language("English")


if __name__ == "__main__":
    unittest.main()
