"""The frozen build can reach every module the app imports lazily.

The spec no longer ships the package's `.py` files as data, so a frozen
build reaches the dialogs only through `hiddenimports`. Those dialogs are
imported inside the handlers that open them, which means a missing entry
does not fail at startup — it fails when a user clicks a menu item.

`main.self_test()` is what a packaged build runs to prove the imports
resolve (`PasswordVault.exe --self-test`). These tests keep its list and
the spec's list from drifting apart, which is the failure this whole
arrangement is guarding against.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SPEC = REPO / "PasswordVault.spec"


def spec_hidden_imports() -> set[str]:
    """The hiddenimports list, read out of the spec without executing it."""
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "Analysis":
            continue
        for kw in node.keywords:
            if kw.arg == "hiddenimports":
                return {e.value for e in kw.value.elts
                        if isinstance(e, ast.Constant)}
    raise AssertionError("no hiddenimports found in the spec")


class SpecTests(unittest.TestCase):
    def test_the_spec_ships_no_package_source(self):
        """Readable source inside a one-file exe is not a build artifact
        anyone asked for; the hidden imports cover the lazy modules."""
        text = SPEC.read_text(encoding="utf-8")
        self.assertNotIn("_pkg_datas", text)
        self.assertNotIn("endswith('.py')", text)

    def test_every_lazy_module_is_a_hidden_import(self):
        import main

        hidden = spec_hidden_imports()
        missing = sorted(set(main.LAZY_MODULES) - hidden)
        self.assertEqual(
            missing, [],
            "modules the app imports lazily but the spec does not list:\n  "
            + "\n  ".join(missing))

    def test_every_hidden_import_is_a_real_module(self):
        import importlib

        for name in sorted(spec_hidden_imports()):
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_the_list_is_not_trusted_to_be_complete(self):
        """Every module main.py imports inside a function is listed.

        The check above runs one way only: it catches a module dropped
        from the spec, not one that was never written down anywhere. A
        dialog imported inside the handler that opens it and named in
        neither list passes every other test here and fails when a user
        clicks the menu item in a frozen build -- the one place nobody is
        watching.

        So the list is compared against what main.py actually does,
        rather than against another list a person maintains. Reading the
        file beats remembering to edit it; a hand-kept list of files is
        how 22 untranslated strings once shipped green.
        """
        import importlib.util

        import main

        tree = ast.parse((REPO / "main.py").read_text(encoding="utf-8"))
        lazy = set()
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Import):
                    lazy.update(a.name for a in node.names
                                if a.name.startswith("password_vault"))
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if not base.startswith("password_vault"):
                        continue
                    for alias in node.names:
                        # `from p import q` is a module when p.q is one,
                        # and a name inside p when it is not.
                        candidate = f"{base}.{alias.name}"
                        try:
                            found = importlib.util.find_spec(candidate)
                        except (ImportError, AttributeError,
                                ValueError):
                            found = None
                        lazy.add(candidate if found else base)

        missing = sorted(lazy - set(main.LAZY_MODULES))
        self.assertEqual(
            missing, [],
            "imported inside a function but absent from LAZY_MODULES, so "
            "nothing proves a frozen build can reach them:\n  "
            + "\n  ".join(missing))

    def test_the_icon_is_still_shipped(self):
        self.assertIn("('icon.ico', '.')",
                      SPEC.read_text(encoding="utf-8"))


class SelfTestTests(unittest.TestCase):
    def test_self_test_passes_from_source(self):
        import main
        self.assertEqual(main.self_test(), 0)

    def test_the_lazy_list_covers_the_dialogs(self):
        """Every dialog module is imported inside a handler, so every one
        of them has to be on the list.

        Compared as whole module names. Matching on the last word instead
        meant `ui.dialogs.settings` counted as covered because
        `password_vault.settings` was on the list -- a different module
        entirely, and the one dialog that most needed checking passed
        without being there.
        """
        import main

        dialogs = sorted(
            f"password_vault.ui.dialogs.{p.stem}"
            for p in (REPO / "password_vault" / "ui" / "dialogs")
            .glob("*.py") if p.stem != "__init__")
        missing = [d for d in dialogs if d not in set(main.LAZY_MODULES)]
        self.assertEqual(missing, [])

    def test_self_test_reports_a_missing_module(self):
        """The check has to be able to fail, or it proves nothing."""
        import main

        original = main.LAZY_MODULES
        main.LAZY_MODULES = original + ("password_vault.not_a_module",)
        try:
            self.assertEqual(main.self_test(), 1)
        finally:
            main.LAZY_MODULES = original


if __name__ == "__main__":
    unittest.main()
