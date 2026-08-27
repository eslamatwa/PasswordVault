"""Breach check against a stubbed Have I Been Pwned range endpoint.

The network call is the only thing replaced. Everything the check actually
decides — what leaves the machine, how responses are grouped and cached,
and what a failed request reports — runs for real.

MVP.md listed the failure path as hand-tested only; it is the one that
matters most, because a network error must read as "unknown" rather than
as "safe".
"""

from __future__ import annotations

import hashlib
import threading
import unittest
from unittest import mock

from password_vault import security


def sha1_of(password: str) -> tuple[str, str]:
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return digest[:5], digest[5:]


def run_check(entries, fetch):
    """Run check_hibp_batch with *fetch* stubbed, and wait for the result."""
    done = threading.Event()
    box: dict = {}
    progress: list[tuple[int, int]] = []

    def on_done(results):
        box["results"] = results
        done.set()

    def on_progress(current, total):
        progress.append((current, total))

    with mock.patch.object(security, "_fetch_hibp_range", fetch):
        security.check_hibp_batch(entries, on_progress, on_done)
        assert done.wait(10), "the breach check never called done_cb"
    return box["results"], progress


class BreachCheckTests(unittest.TestCase):
    def test_a_breached_password_reports_its_count(self):
        prefix, suffix = sha1_of("password123")
        entries = [{"id": "a", "password": "password123"}]
        results, _ = run_check(entries, lambda p: {suffix: 4242})
        self.assertEqual(results, {"a": 4242})

    def test_a_clean_password_reports_zero(self):
        entries = [{"id": "a", "password": "unique-and-unbreached"}]
        results, _ = run_check(entries, lambda p: {"SOMEOTHERSUFFIX": 9})
        self.assertEqual(results, {"a": 0})

    def test_a_network_error_reports_unknown_not_safe(self):
        """-1 means "could not check". Reporting 0 would say "safe"."""
        entries = [{"id": "a", "password": "password123"}]

        def boom(_prefix):
            raise OSError("no network")

        results, _ = run_check(entries, boom)
        self.assertEqual(results, {"a": -1})

    def test_a_malformed_response_reports_unknown(self):
        entries = [{"id": "a", "password": "password123"}]

        def bad(_prefix):
            raise ValueError("garbage body")

        results, _ = run_check(entries, bad)
        self.assertEqual(results, {"a": -1})

    def test_an_entry_without_a_password_is_not_requested(self):
        entries = [{"id": "a", "password": ""}]
        calls = []

        def fetch(prefix):
            calls.append(prefix)
            return {}

        results, _ = run_check(entries, fetch)
        self.assertEqual(results, {"a": 0})
        self.assertEqual(calls, [])

    def test_only_the_hash_prefix_would_leave_the_machine(self):
        """The k-anonymity guarantee, asserted rather than assumed."""
        entries = [{"id": "a", "password": "password123"}]
        prefix, _ = sha1_of("password123")
        seen = []

        def fetch(p):
            seen.append(p)
            return {}

        run_check(entries, fetch)
        self.assertEqual(seen, [prefix])
        self.assertEqual(len(seen[0]), 5)

    def test_one_request_per_distinct_password(self):
        """A vault full of reuse costs one request, not one per entry."""
        entries = [{"id": str(i), "password": "reused"} for i in range(20)]
        calls = []

        def fetch(prefix):
            calls.append(prefix)
            return {}

        results, _ = run_check(entries, fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 20)

    def test_passwords_sharing_a_prefix_are_fetched_once(self):
        entries = [{"id": "a", "password": "one"},
                   {"id": "b", "password": "two"}]
        calls = []

        def fetch(prefix):
            calls.append(prefix)
            return {}

        run_check(entries, fetch)
        # Two distinct secrets, so at most two requests — and exactly one
        # per distinct prefix.
        self.assertEqual(len(calls), len(set(calls)))

    def test_progress_reaches_the_total(self):
        entries = [{"id": "a", "password": "one"},
                   {"id": "b", "password": "two"},
                   {"id": "c", "password": ""}]
        _, progress = run_check(entries, lambda p: {})
        self.assertTrue(progress, "no progress was reported")
        done, total = progress[-1]
        self.assertEqual(total, 3)
        self.assertEqual(done, 3)

    def test_a_mix_of_breached_clean_and_failed_is_reported_per_entry(self):
        _, breached_suffix = sha1_of("breached")
        entries = [{"id": "bad", "password": "breached"},
                   {"id": "good", "password": "clean"},
                   {"id": "err", "password": "failing"}]
        fail_prefix, _ = sha1_of("failing")

        def fetch(prefix):
            if prefix == fail_prefix:
                raise OSError("timeout")
            return {breached_suffix: 7}

        results, _ = run_check(entries, fetch)
        self.assertEqual(results["bad"], 7)
        self.assertEqual(results["good"], 0)
        self.assertEqual(results["err"], -1)


class RangeParsingTests(unittest.TestCase):
    """`_fetch_hibp_range` parses the real endpoint's text format."""

    def _fetch_with_body(self, body: str):
        class FakeResponse:
            def read(self_inner):
                return body.encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        with mock.patch.object(security.urllib.request, "urlopen",
                               return_value=FakeResponse()):
            return security._fetch_hibp_range("ABCDE")

    def test_lines_are_parsed_into_suffix_counts(self):
        out = self._fetch_with_body("AAAA:12\r\nBBBB:3\r\n")
        self.assertEqual(out, {"AAAA": 12, "BBBB": 3})

    def test_blank_and_malformed_lines_are_skipped(self):
        out = self._fetch_with_body("AAAA:12\n\ngarbage\nBBBB:notanumber\n")
        self.assertEqual(out, {"AAAA": 12})

    def test_padding_is_requested_so_size_reveals_nothing(self):
        """Without padding, the response length leaks how many hashes
        share the prefix."""
        captured = {}

        class FakeResponse:
            def read(self_inner):
                return b""

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured["headers"] = req.headers
            captured["url"] = req.full_url
            return FakeResponse()

        with mock.patch.object(security.urllib.request, "urlopen",
                               fake_urlopen):
            security._fetch_hibp_range("ABCDE")

        lowered = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(lowered.get("add-padding"), "true")
        # The whole request is the 5-character prefix and nothing else:
        # no query string, no fragment, no suffix.
        self.assertTrue(captured["url"].endswith("/range/ABCDE"))
        self.assertNotIn("?", captured["url"])
        self.assertNotIn("#", captured["url"])

    def test_the_password_and_its_full_hash_never_reach_the_url(self):
        password = "hunter2"
        prefix, suffix = sha1_of(password)
        captured = {}

        class FakeResponse:
            def read(self_inner):
                return b""

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return FakeResponse()

        with mock.patch.object(security.urllib.request, "urlopen",
                               fake_urlopen):
            security._fetch_hibp_range(prefix)

        self.assertIn(prefix, captured["url"])
        self.assertNotIn(suffix, captured["url"])
        self.assertNotIn(password, captured["url"])


if __name__ == "__main__":
    unittest.main()
