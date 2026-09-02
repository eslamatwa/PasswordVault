"""Finding the SSH clients that are actually on the machine.

The dropdown only ever offers what was found, so a client installed
somewhere the search does not look is indistinguishable from one that is
not installed at all — which is how a missing PuTTY was reported. The
fixed paths cover the installers; PATH covers winget shims and portable
copies, and a setting covers whatever is left.
"""

from __future__ import annotations

import os

import pytest

# `main` is imported inside the fixtures, never at module scope.
#
# Collection imports every test module before anything runs, so a
# module-level `import main` would build the app's CustomTkinter global
# state once at collection — and `_live_app` then clears `sys.modules`
# and builds it again. That is the same module-identity trap `app_crypto`
# and `app_widgets` exist for, and it is worth avoiding on its own.
#
# It is not, however, what caused the suite-wide Tcl failures that were
# being chased when this comment was first written. That was stale
# bytecode from two throwaway plugin files. Recorded so the next person
# does not read a fix into a precaution.


def _vault():
    import main

    return main.PasswordVault


@pytest.fixture
def detect():
    return _vault()._detect_ssh_clients


def _names(clients):
    return [name for name, _ in clients]


class TestOrder:
    def test_mobaxterm_leads_when_it_is_installed(self, detect,
                                                  monkeypatch):
        """Pressing Enter picks the first one, and someone who installed
        MobaXterm is not reaching for PuTTY by preference."""
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        assert _names(detect())[0] == "MobaXterm"

    def test_windows_ssh_comes_last(self, detect, monkeypatch):
        """It is the fallback everyone already has."""
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        assert _names(detect())[-1] == "Windows SSH"


class TestPuttyIsFound:
    def test_in_program_files(self, detect, monkeypatch):
        monkeypatch.setattr(
            os.path, "isfile",
            lambda p: p.lower().endswith("putty\\putty.exe"))
        assert "PuTTY" in _names(detect())

    def test_as_a_winget_shim_on_path(self, detect, monkeypatch):
        """winget puts a shim in its Links folder and on PATH, nowhere
        near Program Files. This is the case that was missing."""
        monkeypatch.setattr(os.path, "isfile", lambda _p: False)
        import main as main_module

        monkeypatch.setattr(
            main_module.shutil, "which",
            lambda name: r"C:\shims\putty.exe" if name == "putty" else None)
        clients = detect()
        assert ("PuTTY", r"C:\shims\putty.exe") in clients

    def test_it_is_absent_when_it_really_is_absent(self, detect,
                                                  monkeypatch):
        """The opposite failure: offering a client that is not there
        means a dropdown entry that cannot start anything."""
        import main as main_module

        monkeypatch.setattr(os.path, "isfile", lambda _p: False)
        monkeypatch.setattr(main_module.shutil, "which", lambda _n: None)
        assert "PuTTY" not in _names(detect())


class TestACustomClient:
    def test_a_configured_path_is_offered(self, detect, tmp_path):
        exe = tmp_path / "kitty.exe"
        exe.write_text("")
        clients = detect({"ssh_client_path": str(exe)})
        assert ("kitty", str(exe)) in clients

    def test_it_comes_last(self, detect, tmp_path, monkeypatch):
        """Detection is the better guess; the manual one is the backstop."""
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        exe = tmp_path / "kitty.exe"
        clients = detect({"ssh_client_path": str(exe)})
        assert _names(clients)[-1] == "kitty"

    def test_a_path_that_no_longer_exists_is_skipped(self, detect):
        """Offering a client that has been uninstalled would fail at
        launch with an error about a missing file."""
        clients = detect({"ssh_client_path": r"C:\gone\nothing.exe"})
        assert "nothing" not in _names(clients)

    def test_it_does_not_duplicate_a_detected_client(self, detect,
                                                     tmp_path,
                                                     monkeypatch):
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        exe = tmp_path / "putty.exe"
        names = _names(detect({"ssh_client_path": str(exe)}))
        assert names.count("PuTTY") == 1, names
        assert "putty" not in [n for n in names if n != "PuTTY"]

    def test_no_setting_changes_nothing(self, detect, monkeypatch):
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        assert _names(detect({})) == _names(detect())


class TestEveryClientCanBeLaunched:
    def test_each_detected_client_builds_a_command(self, detect,
                                                   monkeypatch):
        """A name in the dropdown that ssh_command does not know would
        silently fall through to the Windows SSH branch."""
        monkeypatch.setattr(os.path, "isfile", lambda _p: True)
        for name, path in detect():
            cmd = _vault().ssh_command(name, path, "10.0.0.5", "root", 22)
            assert cmd, f"{name} produced no command"
            assert any(path in str(part) or "cmd" == part
                       for part in cmd), f"{name}: {cmd}"


class TestTheSettingActuallySurvives:
    """The gap that let a dead feature ship.

    Every test above hands `_detect_ssh_clients` a dict directly, which
    skips the part that turned out to matter: settings are validated
    against a schema on load, and an unknown key is dropped with a
    warning nobody reads. `ssh_client_path` was not in that schema, so
    the setting worked in tests and did nothing at all for a real user.

    These go through `load_settings`, the way the app gets them.
    """

    def _round_trip(self, tmp_path, monkeypatch, value):
        import importlib
        import json

        monkeypatch.setenv("APPDATA", str(tmp_path))
        settings = importlib.reload(
            importlib.import_module("password_vault.settings"))
        os.makedirs(os.path.dirname(settings.SETTINGS_FILE), exist_ok=True)
        with open(settings.SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"ssh_client_path": value}, fh)
        return settings.load_settings().get("ssh_client_path")

    def test_a_stored_path_comes_back(self, tmp_path, monkeypatch):
        wanted = r"C:\tools\kitty.exe"
        assert self._round_trip(tmp_path, monkeypatch, wanted) == wanted

    def test_it_has_a_default_so_nothing_has_to_guess(self):
        import password_vault.settings as settings

        assert "ssh_client_path" in settings.DEFAULT_SETTINGS
        assert settings.DEFAULT_SETTINGS["ssh_client_path"] == ""

    def test_an_absurd_value_is_still_refused(self, tmp_path, monkeypatch):
        """Accepting the key must not mean accepting anything under it."""
        assert self._round_trip(tmp_path, monkeypatch, "x" * 900) in (
            "", None)

    def test_a_path_on_an_unmounted_drive_is_kept(self, tmp_path,
                                                  monkeypatch):
        """Settings load while the vault is still locked, so a network
        drive may not be there yet. Existence is checked at detection
        time, not here -- dropping it would lose the setting for good."""
        wanted = r"Z:\portable\putty.exe"
        assert self._round_trip(tmp_path, monkeypatch, wanted) == wanted
