"""What each SSH client actually receives.

Reported symptom: a username typed into the entry arrived at MobaXterm
wrong. The cause was not MobaXterm — it was `_sanitize_shell_arg`, an
allowlist filter that *deleted* every character outside a small set from
both the username and the host. `svc+deploy` connected as `svcdeploy`, and
a non-Latin username was erased to an empty string, so the client prompted
as though no user had been given at all.

The filter existed to prevent command injection, but every client is
launched with an argument *list*, which no shell parses. The one place a
shell is genuinely involved is MobaXterm's `-newtab`, which takes a single
command string — verified against MobaXterm 26.3 by having it run a script
that printed its own argv:

    -newtab "…/fake_ssh -l 'DOMAIN\\tester' myhost"
    -> arg1=[-l]  arg2=[DOMAIN\\tester]  arg3=[myhost]

so the string is shell-split and `shlex.quote` is exactly the right
quoting for it.

These tests pin the argument list for each client, and assert that a
credential is never silently altered.
"""

from __future__ import annotations

import shlex
import unittest

import main


CMD = main.PasswordVault.ssh_command
CHECK = main.PasswordVault._check_remote_arg


class PuttyTests(unittest.TestCase):
    def test_user_and_host(self):
        self.assertEqual(
            CMD("PuTTY", r"C:\putty.exe", "srv.example", "root", 22),
            [r"C:\putty.exe", "-ssh", "-l", "root", "srv.example"])

    def test_a_non_default_port_uses_capital_p(self):
        """PuTTY spells it -P; ssh spells it -p."""
        cmd = CMD("PuTTY", "putty.exe", "srv", "root", 2222)
        self.assertIn("-P", cmd)
        self.assertNotIn("-p", cmd)
        self.assertEqual(cmd[cmd.index("-P") + 1], "2222")

    def test_the_default_port_is_left_off(self):
        self.assertNotIn("-P", CMD("PuTTY", "putty.exe", "srv", "root", 22))

    def test_no_user_means_no_dash_l(self):
        self.assertEqual(CMD("PuTTY", "putty.exe", "srv", "", 22),
                         ["putty.exe", "-ssh", "srv"])

    def test_the_host_is_the_last_argument(self):
        self.assertEqual(
            CMD("PuTTY", "putty.exe", "srv", "root", 2222)[-1], "srv")


class MobaXtermTests(unittest.TestCase):
    def _ssh_string(self, host, user, port=22):
        cmd = CMD("MobaXterm", "moba.exe", host, user, port)
        self.assertEqual(cmd[0], "moba.exe")
        self.assertEqual(cmd[1], "-newtab")
        return cmd[2]

    def test_the_command_is_one_string_after_newtab(self):
        cmd = CMD("MobaXterm", "moba.exe", "srv", "root", 22)
        self.assertEqual(len(cmd), 3)

    def test_the_string_splits_back_to_the_intended_arguments(self):
        """MobaXterm's shell splits this string; shlex is the same rules."""
        got = shlex.split(self._ssh_string("srv.example", "root"))
        self.assertEqual(got, ["ssh", "-l", "root", "srv.example"])

    def test_a_domain_user_keeps_its_backslash(self):
        user = "DOMAIN\\tester"
        got = shlex.split(self._ssh_string("srv", user))
        self.assertEqual(got[2], user)

    def test_a_username_with_a_plus_is_not_altered(self):
        """The reported symptom: this used to arrive as 'svcdeploy'."""
        got = shlex.split(self._ssh_string("srv", "svc+deploy"))
        self.assertEqual(got[2], "svc+deploy")

    def test_a_username_with_a_dollar_is_not_altered(self):
        got = shlex.split(self._ssh_string("srv", "user$prod"))
        self.assertEqual(got[2], "user$prod")

    def test_a_non_latin_username_survives(self):
        """It used to be erased to an empty string."""
        got = shlex.split(self._ssh_string("srv", "عبدالله"))
        self.assertEqual(got[2], "عبدالله")

    def test_a_username_with_a_space_stays_one_argument(self):
        got = shlex.split(self._ssh_string("srv", "my user"))
        self.assertEqual(got[2], "my user")
        self.assertEqual(len(got), 4)

    def test_a_username_with_a_quote_stays_one_argument(self):
        got = shlex.split(self._ssh_string("srv", "o'brien"))
        self.assertEqual(got[2], "o'brien")

    def test_the_port_uses_lowercase_p(self):
        got = shlex.split(self._ssh_string("srv", "root", 2222))
        self.assertEqual(got, ["ssh", "-l", "root", "-p", "2222", "srv"])

    def test_options_come_before_the_host(self):
        got = shlex.split(self._ssh_string("srv", "root", 2222))
        self.assertEqual(got[-1], "srv")


class WindowsSshTests(unittest.TestCase):
    def test_it_runs_through_cmd_so_the_console_stays_open(self):
        cmd = CMD("Windows SSH", "ssh.exe", "srv", "root", 22)
        self.assertEqual(cmd[:2], ["cmd", "/k"])

    def test_the_ssh_arguments_follow(self):
        cmd = CMD("Windows SSH", "ssh.exe", "srv", "root", 22)
        self.assertEqual(cmd[2:], ["ssh.exe", "-l", "root", "srv"])

    def test_the_port_precedes_the_host(self):
        cmd = CMD("Windows SSH", "ssh.exe", "srv", "root", 2222)
        self.assertEqual(cmd[2:],
                         ["ssh.exe", "-l", "root", "-p", "2222", "srv"])

    def test_the_username_is_passed_through_untouched(self):
        for user in ["svc+deploy", "user$prod", "عبدالله", "o'brien",
                     "DOMAIN\\tester", "first.last@corp.com"]:
            with self.subTest(user=user):
                cmd = CMD("Windows SSH", "ssh.exe", "srv", user, 22)
                self.assertIn(user, cmd)


class ArgumentCheckTests(unittest.TestCase):
    """Refusing a bad value beats quietly rewriting it."""

    def test_ordinary_usernames_pass(self):
        for user in ["root", "ubuntu", "ec2-user", "svc+deploy",
                     "user$prod", "first.last@corp.com", "DOMAIN\\tester",
                     "عبدالله", "o'brien", "my user", "user#1", "user(1)"]:
            with self.subTest(user=user):
                self.assertIsNone(CHECK(user, "Username"))

    def test_ordinary_hosts_pass(self):
        for host in ["10.0.0.5", "srv.example.com", "db01", "fe80::1",
                     "host-name.sub.domain"]:
            with self.subTest(host=host):
                self.assertIsNone(CHECK(host, "Host"))

    def test_command_separators_are_refused(self):
        for bad in ["srv & calc", "srv | more", "srv > f", "srv < f",
                    "srv ^ x", 'srv " x', "srv ` x", "srv ; x"]:
            with self.subTest(value=bad):
                self.assertIsNotNone(CHECK(bad, "Host"))

    def test_newlines_and_nulls_are_refused(self):
        for bad in ["srv\nmore", "srv\rmore", "srv\tmore", "srv\x00"]:
            with self.subTest(value=repr(bad)):
                self.assertIsNotNone(CHECK(bad, "Host"))

    def test_a_leading_hyphen_is_refused(self):
        """Every client reads its arguments as options first."""
        self.assertIsNotNone(CHECK("-oProxyCommand=calc", "Host"))
        self.assertIsNotNone(CHECK("-l", "Username"))

    def test_an_empty_value_passes(self):
        """Emptiness is handled by the caller, not by this check."""
        self.assertIsNone(CHECK("", "Username"))

    def test_the_message_names_the_field_and_the_characters(self):
        message = CHECK("srv&calc", "Host / IP")
        self.assertIn("Host / IP", message)
        self.assertIn("&", message)


class ClientOrderTests(unittest.TestCase):
    def test_mobaxterm_leads_when_present(self):
        """The first entry is what Enter picks."""
        import os
        from unittest import mock

        real_isfile = os.path.isfile
        moba = os.path.join("C:\\PF86", "Mobatek", "MobaXterm",
                            "MobaXterm.exe")
        putty = os.path.join("C:\\PF", "PuTTY", "putty.exe")

        def fake_isfile(path):
            if path in (moba, putty):
                return True
            return False if "OpenSSH" in str(path) else real_isfile(path)

        env = {"ProgramFiles(x86)": "C:\\PF86", "ProgramFiles": "C:\\PF",
               "LOCALAPPDATA": "C:\\LA", "SystemRoot": "C:\\Windows"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(os.path, "isfile", fake_isfile), \
                mock.patch.object(main.shutil, "which", return_value=None):
            names = [n for n, _ in
                     main.PasswordVault._detect_ssh_clients()]
        self.assertEqual(names[0], "MobaXterm")
        self.assertIn("PuTTY", names)


if __name__ == "__main__":
    unittest.main()
