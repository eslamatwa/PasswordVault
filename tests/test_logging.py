"""The log, and keeping the test suite out of the user's copy of it.

`password_vault/__init__.py` opens %APPDATA%/PasswordVault/vault.log when
the package is imported and attaches it to the root logger. That is the
only record of anything a user reports, so it matters that the suite does
not write to it: a run of this suite produces thousands of lines, and
rotation then discards the real history. It had been doing exactly that,
and the loss only surfaced when a user reported behaviour that could not
be reproduced and the log turned out to hold nothing but test output.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import pathlib

import password_vault

from tests.conftest import LOG_SANDBOX, REAL_APPDATA

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _file_handlers():
    """The app's own log handlers.

    pytest attaches a file handler pointing at the null device, so this
    filters by name rather than trusting every handler that has a file.
    """
    return [h for h in logging.getLogger().handlers
            if os.path.basename(
                getattr(h, "baseFilename", "") or "") == "vault.log"]


class TestIsolation:
    def test_nothing_logs_outside_the_sandbox(self):
        outside = [h.baseFilename for h in _file_handlers()
                   if not os.path.abspath(h.baseFilename).startswith(
                       os.path.abspath(LOG_SANDBOX))]
        assert not outside, f"writing to a real log: {outside}"

    def test_appdata_never_points_at_the_real_one(self):
        """Everything the app writes hangs off this, not just the log.

        Not an equality check against the sandbox: `_live_app` moves
        APPDATA again, to its own temp directory, which is fine. What
        must never happen is a test writing where the installed copy of
        the app keeps its vault.
        """
        current = os.path.abspath(os.environ["APPDATA"])
        assert current != os.path.abspath(REAL_APPDATA), \
            "a test is writing to the real application data directory"

    def test_importing_the_package_is_what_sets_logging_up(self):
        """There is no explicit init call: `password_vault/__init__.py`
        attaches the handler at import. Worth pinning, because it is why
        the redirect in conftest has to happen at import time too."""
        assert password_vault.APP_VERSION
        assert _file_handlers(), "importing the package attached no handler"

    def test_the_app_is_actually_logging_somewhere(self):
        """The opposite failure: isolating the log by breaking it."""
        assert _file_handlers(), "no file handler is attached at all"
        log = logging.getLogger("PasswordVault")
        assert log.getEffectiveLevel() <= logging.INFO, \
            "INFO would be dropped, so the lifecycle lines never appear"
        assert log.propagate, \
            "the app logger no longer reaches the root handler"


class TestItRotates:
    def test_the_handler_has_a_size_cap_and_backups(self):
        """An uncapped log fills the disk; one with no backups loses the
        run before last, which is usually the one being asked about."""
        rotating = [h for h in _file_handlers()
                    if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert rotating, "the log is not set up to rotate"
        for handler in rotating:
            assert handler.maxBytes > 0
            assert handler.backupCount >= 1


class TestLifecycleIsVisible:
    """A user reporting a window that opens and closes on its own should
    leave a readable trail without being talked through a debug flag."""

    def test_every_window_transition_is_logged_at_info(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        for phrase in ("Starting Password Vault",
                       "UI ready",
                       "Minimising to the floating widget",
                       "Restoring the main window",
                       "Application exiting",
                       "Main loop returned"):
            assert phrase in source, f"nothing logs {phrase!r}"
            index = source.index(phrase)
            call = source.rfind("log.", max(0, index - 200), index)
            assert call != -1, f"{phrase!r} is not inside a log call"
            assert source[call:index].startswith(
                ("log.info", "log.warning", "log.error", "log.critical")), \
                f"{phrase!r} is logged below INFO, so it will not appear"

    def test_a_crash_is_recorded_before_it_propagates(self):
        """A windowed build has no console, so an unhandled exception
        would otherwise leave nothing at all behind."""
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        assert "log.exception(" in source, \
            "an unhandled exception is never written to the log"


class TestSecrets:
    def test_no_log_call_passes_a_secret_as_an_argument(self):
        """The rule is that call sites log what happened, not what was in
        the entry. Checked against the arguments only: the app is called
        'Password Vault', so the word appears in plenty of harmless
        message text and matching on the whole line just cries wolf.
        """
        risky = ("password", "passwd", "secret", "plaintext", "master",
                 "self.key", "token")
        offenders = []
        files = [ROOT / "main.py"] + sorted(
            (ROOT / "password_vault").rglob("*.py"))
        for path in files:
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith("log."):
                    continue
                # Everything after the closing quote of the message is an
                # argument; the message itself is allowed to say anything.
                without_text = _strip_string_literals(stripped)
                lowered = without_text.lower()
                if any(word in lowered for word in risky):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{number}: {stripped}")
        assert not offenders, \
            "a log call may be writing a secret:\n" + "\n".join(offenders)


def _strip_string_literals(line: str) -> str:
    """Blank out quoted text, leaving the code around it."""
    out, quote, escaped = [], None, False
    for char in line:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        out.append(char)
    return "".join(out)


class TestTheStripper:
    """The check above is only worth having if this part is right."""

    def test_it_keeps_arguments_and_drops_message_text(self):
        assert "password" not in _strip_string_literals(
            'log.info("Password changed")').lower()
        assert "password" in _strip_string_literals(
            'log.info("changed to %s", password)').lower()

    def test_it_survives_an_escaped_quote(self):
        assert _strip_string_literals(
            'log.info("say \\"hi\\"", value)').strip() == "log.info(, value)"
