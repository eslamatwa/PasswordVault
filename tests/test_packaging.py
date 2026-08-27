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

    def test_the_icon_is_still_shipped(self):
        self.assertIn("('icon.ico', '.')",
                      SPEC.read_text(encoding="utf-8"))


class SelfTestTests(unittest.TestCase):
    def test_self_test_passes_from_source(self):
        import main
        self.assertEqual(main.self_test(), 0)

    def test_the_lazy_list_covers_the_dialogs(self):
        """Every dialog module is imported inside a handler, so every one
        of them has to be on the list."""
        import main

        dialogs = sorted(
            p.stem for p in (REPO / "password_vault" / "ui" / "dialogs")
            .glob("*.py") if p.stem != "__init__")
        listed = {name.rsplit(".", 1)[-1] for name in main.LAZY_MODULES}
        missing = [d for d in dialogs if d not in listed]
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
