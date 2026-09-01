"""SSH private keys: what kind, whether locked, and making one.

The question this has to answer is "does this key have a passphrase?",
and it has to answer it *without* the passphrase. Getting it wrong is not
a crash either way: say yes when it is no and the user is taught to type
their account password into a box nothing will use; say no when it is yes
and they are left at a prompt with an empty clipboard.

It cannot be answered from the header. `ssh-keygen` writes
`-----BEGIN OPENSSH PRIVATE KEY-----` whether or not you gave it a
passphrase — verified below against keys this suite generates with the
real `ssh-keygen` when it is present.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from password_vault import sshkeys

KEYGEN = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "OpenSSH", "ssh-keygen.exe")
HAS_KEYGEN = sys.platform == "win32" and os.path.isfile(KEYGEN)
needs_keygen = pytest.mark.skipif(
    not HAS_KEYGEN, reason="ssh-keygen is not available here")


@pytest.fixture(scope="module")
def real_keys(tmp_path_factory):
    """Keys made by the tool that made the user's keys."""
    if not HAS_KEYGEN:
        pytest.skip("ssh-keygen is not available here")
    folder = tmp_path_factory.mktemp("keys")
    made = {}
    for name, kind, passphrase in (("plain", "ed25519", ""),
                                   ("locked", "ed25519", "hunter2"),
                                   ("rsa_locked", "rsa", "hunter2")):
        path = folder / name
        subprocess.run(
            [KEYGEN, "-t", kind, "-f", str(path), "-N", passphrase, "-q"],
            check=True, capture_output=True)
        made[name] = path
    return made


class TestTheHeaderIsNotEnough:
    @needs_keygen
    def test_locked_and_unlocked_keys_look_identical(self, real_keys):
        """The whole reason the body has to be parsed."""
        heads = {name: path.read_text().splitlines()[0]
                 for name, path in real_keys.items()}
        assert len(set(heads.values())) == 1, heads
        assert "OPENSSH PRIVATE KEY" in list(heads.values())[0]


class TestDetectingAPassphrase:
    @needs_keygen
    @pytest.mark.parametrize("name,expected", [
        ("plain", False), ("locked", True), ("rsa_locked", True),
    ])
    def test_against_real_keys(self, real_keys, name, expected):
        found = sshkeys.read(str(real_keys[name]))
        assert found["kind"] == sshkeys.OPENSSH
        assert found["encrypted"] is expected, found

    @needs_keygen
    def test_it_never_needs_the_passphrase_to_answer(self, real_keys):
        """It reads a cipher name, it does not attempt a decryption."""
        found = sshkeys.read(str(real_keys["locked"]))
        assert found["encrypted"] is True
        assert not found["problem"]

    def test_an_encrypted_pkcs8_key(self):
        from cryptography.hazmat.primitives import serialization as ser
        from cryptography.hazmat.primitives.asymmetric import ed25519

        key = ed25519.Ed25519PrivateKey.generate()
        blob = key.private_bytes(
            ser.Encoding.PEM, ser.PrivateFormat.PKCS8,
            ser.BestAvailableEncryption(b"secret"))
        assert sshkeys.describe(blob)["encrypted"] is True

    def test_a_plain_pkcs8_key(self):
        from cryptography.hazmat.primitives import serialization as ser
        from cryptography.hazmat.primitives.asymmetric import ed25519

        key = ed25519.Ed25519PrivateKey.generate()
        blob = key.private_bytes(
            ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption())
        assert sshkeys.describe(blob)["encrypted"] is False

    @pytest.mark.parametrize("body,encrypted", [
        (b"PuTTY-User-Key-File-3: ssh-ed25519\nEncryption: none\n", False),
        (b"PuTTY-User-Key-File-2: ssh-rsa\nEncryption: aes256-cbc\n", True),
    ])
    def test_a_putty_key_says_so_outright(self, body, encrypted):
        found = sshkeys.describe(body)
        assert found["kind"] == sshkeys.PPK
        assert found["encrypted"] is encrypted


class TestWhenItCannotTell:
    """`None` is not `False`. Showing "no passphrase needed" for a key
    that could not be read would be a guess dressed as an answer."""

    @pytest.mark.parametrize("junk", [
        b"", b"not a key at all", b"-----BEGIN OPENSSH PRIVATE KEY-----\n"
                                  b"!!!not base64!!!\n-----END-----",
    ])
    def test_unreadable_input_reports_unknown(self, junk):
        assert sshkeys.describe(junk)["encrypted"] is None

    def test_a_public_key_is_named_as_the_mistake_it_is(self):
        """Picking the .pub is the easiest wrong file to pick."""
        found = sshkeys.describe(b"ssh-ed25519 AAAAC3Nza... user@host\n")
        assert found["encrypted"] is None
        assert ".pub" in found["problem"]

    def test_something_enormous_is_refused_before_being_parsed(self):
        found = sshkeys.describe(b"x" * (sshkeys.MAX_KEY_BYTES + 10))
        assert found["encrypted"] is None
        assert "large" in found["problem"]

    def test_a_missing_file_explains_itself(self):
        found = sshkeys.read(r"C:\nowhere\nothing.pem")
        assert found["encrypted"] is None
        assert found["problem"]


class TestGenerating:
    def test_it_makes_a_usable_pair(self):
        private, public = sshkeys.generate("ed25519", comment="vault")
        assert private.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
        assert public.startswith("ssh-ed25519 ")
        assert public.endswith(" vault")

    def test_a_generated_key_has_no_passphrase(self):
        """Deliberate: the vault is already the protection, and a
        passphrase on top would be typed at every connection while
        stopping nobody who already has the decrypted vault."""
        private, _public = sshkeys.generate()
        assert sshkeys.describe(private)["encrypted"] is False

    def test_the_public_half_can_be_derived_again(self):
        """It is what gets pasted onto a server, and the private half
        lives in the vault — so it has to be recoverable, not stored."""
        private, public = sshkeys.generate(comment="vault")
        assert sshkeys.public_from_private(private, "vault") == public

    def test_rsa_works_too(self):
        private, public = sshkeys.generate("rsa")
        assert public.startswith("ssh-rsa ")
        assert sshkeys.describe(private)["kind"] == sshkeys.OPENSSH

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(sshkeys.KeyError_):
            sshkeys.generate("magic-beans")

    @needs_keygen
    def test_ssh_keygen_agrees_with_what_we_made(self):
        """The strongest check available: the real tool reads our key and
        derives the same public half."""
        private, public = sshkeys.generate("ed25519")
        path, problem = sshkeys.materialise(private, "check")
        assert not problem, problem
        try:
            out = subprocess.run([KEYGEN, "-y", "-f", path],
                                 capture_output=True, text=True)
            assert out.returncode == 0, out.stderr
            assert out.stdout.split()[:2] == public.split()[:2]
        finally:
            sshkeys.discard(path)


class TestMaterialising:
    """A stored key has to become a file for one connection, because
    every client takes a path and none takes bytes."""

    def test_it_writes_and_removes(self):
        private, _public = sshkeys.generate()
        path, problem = sshkeys.materialise(private, "prod server")
        assert not problem, problem
        try:
            assert os.path.isfile(path)
            assert open(path, encoding="utf-8").read().startswith(
                "-----BEGIN OPENSSH")
        finally:
            sshkeys.discard(path)
        assert not os.path.exists(path), "the private key was left behind"

    def test_discarding_twice_is_safe(self):
        private, _public = sshkeys.generate()
        path, _problem = sshkeys.materialise(private)
        sshkeys.discard(path)
        sshkeys.discard(path)

    def test_discarding_nothing_is_safe(self):
        sshkeys.discard("")

    @needs_keygen
    def test_openssh_accepts_the_permissions(self):
        """Without locking the file down, OpenSSH refuses it with "Bad
        permissions" — which reads as a broken key rather than an ACL,
        and is exactly the failure this guards against."""
        private, _public = sshkeys.generate()
        path, problem = sshkeys.materialise(private)
        assert not problem, problem
        try:
            out = subprocess.run([KEYGEN, "-y", "-f", path],
                                 capture_output=True, text=True)
            assert out.returncode == 0, \
                f"OpenSSH refused the file: {out.stderr.strip()}"
        finally:
            sshkeys.discard(path)

    @pytest.mark.skipif(shutil.which("icacls") is None,
                        reason="icacls is not available here")
    def test_only_one_principal_can_read_it(self):
        private, _public = sshkeys.generate()
        path, _problem = sshkeys.materialise(private)
        try:
            acl = subprocess.run(["icacls", path], capture_output=True,
                                 text=True)
            granted = [line for line in acl.stdout.splitlines()
                       if ":(" in line]
            assert len(granted) == 1, granted
        finally:
            sshkeys.discard(path)

    @pytest.mark.parametrize("name", [
        r"../../evil name", r"..\..\evil", "C:/windows/system32/hosts",
        "a" * 200, "", "🔐 سيرفر",
    ])
    def test_the_name_cannot_escape_the_folder(self, name):
        """The name comes from an entry title, which the user types.

        The property that matters is containment, not the absence of any
        particular character: separators are replaced, so `../../x`
        becomes a long odd filename rather than a path. Asserting "no
        `..` anywhere" would be testing the sanitiser's spelling instead
        of what it is for.
        """
        private, _public = sshkeys.generate()
        path, problem = sshkeys.materialise(private, name)
        assert not problem, problem
        try:
            folder = os.path.realpath(
                os.path.join(os.path.dirname(os.path.realpath(path))))
            assert os.path.basename(folder) == sshkeys.MATERIALISED_DIR, \
                f"{name!r} escaped to {path}"
        finally:
            sshkeys.discard(path)


class TestClientFormats:
    @pytest.mark.parametrize("client", ["Windows SSH", "MobaXterm"])
    def test_an_openssh_key_suits_the_openssh_clients(self, client):
        assert sshkeys.suits(sshkeys.OPENSSH, client) is None

    def test_putty_refuses_an_openssh_key_with_a_reason(self):
        """Handing PuTTY an OpenSSH key fails with a message about the
        file not being recognised, which sounds like the key is broken."""
        why = sshkeys.suits(sshkeys.OPENSSH, "PuTTY")
        assert why and "ppk" in why.lower()

    def test_windows_ssh_refuses_a_ppk_with_a_reason(self):
        why = sshkeys.suits(sshkeys.PPK, "Windows SSH")
        assert why and "OpenSSH" in why

    def test_an_unknown_format_is_not_second_guessed(self):
        """If the format could not be read, the client is left to say so
        rather than this refusing on a guess."""
        assert sshkeys.suits(sshkeys.UNKNOWN, "PuTTY") is None

    def test_an_unknown_client_is_not_second_guessed(self):
        assert sshkeys.suits(sshkeys.OPENSSH, "kitty") is None


class TestReachingTheClient:
    """`-i` on the command line, and the right secret on the clipboard."""

    @pytest.fixture
    def vault(self):
        import main

        return main.PasswordVault

    @pytest.mark.parametrize("client", ["PuTTY", "MobaXterm", "Windows SSH"])
    def test_every_client_is_given_the_key(self, vault, client):
        cmd = vault.ssh_command(client, "client.exe", "10.0.0.5", "root",
                                22, r"C:\keys\prod.pem")
        flat = " ".join(str(part) for part in cmd)
        assert "-i" in flat, f"{client} was not given the key"
        assert "prod.pem" in flat

    @pytest.mark.parametrize("client", ["PuTTY", "MobaXterm", "Windows SSH"])
    def test_no_key_means_no_flag(self, vault, client):
        cmd = vault.ssh_command(client, "client.exe", "10.0.0.5", "root", 22)
        assert "-i" not in " ".join(str(part) for part in cmd)

    def test_a_key_path_with_spaces_survives_mobaxterm(self, vault):
        """MobaXterm's -newtab is one string its own shell splits, so an
        unquoted path with a space arrives as two arguments."""
        import shlex

        cmd = vault.ssh_command("MobaXterm", "moba.exe", "10.0.0.5", "root",
                                22, r"C:\my keys\prod.pem")
        assert len(cmd) == 3
        assert shlex.split(cmd[2])[-3:-1] == ["-i", r"C:\my keys\prod.pem"]


class TestChoosingTheKeyFile:
    @pytest.fixture
    def app_with(self, app):
        def make(**over):
            entry = {"id": "k", "title": "server", "username": "root",
                     "password": "accountpw", "url": "10.0.0.5",
                     "category": "Server"}
            entry.update(over)
            app.data["entries"] = [entry]
            return app, entry
        return make

    def test_no_key_configured_gives_nothing(self, app_with):
        app, entry = app_with()
        assert app.key_for(entry, "Windows SSH") == ("", False, "")

    def test_a_missing_file_is_reported_not_launched(self, app_with):
        """Otherwise the client refuses the login and it reads as wrong
        credentials rather than a moved file."""
        app, entry = app_with(ssh_key_source="file",
                              ssh_key_path=r"C:\gone\nothing.pem")
        path, temporary, problem = app.key_for(entry, "Windows SSH")
        assert path == "" and not temporary
        assert "not there" in problem

    def test_a_real_file_is_used_where_it_lies(self, app_with, tmp_path):
        private, _public = sshkeys.generate()
        target = tmp_path / "id_ed25519"
        target.write_text(private, encoding="utf-8")
        app, entry = app_with(ssh_key_source="file",
                              ssh_key_path=str(target))
        path, temporary, problem = app.key_for(entry, "Windows SSH")
        assert path == str(target), problem
        assert not temporary, "a referenced key must not be copied"

    def test_putty_refuses_an_openssh_key_before_launching(self, app_with,
                                                          tmp_path):
        private, _public = sshkeys.generate()
        target = tmp_path / "id_ed25519"
        target.write_text(private, encoding="utf-8")
        app, entry = app_with(ssh_key_source="file",
                              ssh_key_path=str(target))
        _path, _temp, problem = app.key_for(entry, "PuTTY")
        assert problem and "ppk" in problem.lower()

    def test_a_stored_key_becomes_a_temporary_file(self, app_with):
        private, _public = sshkeys.generate()
        app, entry = app_with(ssh_key_source="stored", ssh_key=private)
        path, temporary, problem = app.key_for(entry, "Windows SSH")
        assert not problem, problem
        try:
            assert temporary, "a stored key has to be written somewhere"
            assert os.path.isfile(path)
        finally:
            app.forget_key_file(path)
        assert not os.path.exists(path), "the private key was left behind"


class TestWhichSecretIsStaged:
    @pytest.fixture
    def staged(self, app, monkeypatch):
        copied = []
        monkeypatch.setattr(
            app, "_copy_to_clipboard",
            lambda text, btn=None, **k: copied.append(text))
        return app, copied

    def test_without_a_key_the_password_goes(self, staged):
        app, copied = staged
        app._stage_password_for_paste(
            {"password": "accountpw", "ssh_key_source": "none"})
        assert copied == ["accountpw"]

    def test_with_a_key_the_passphrase_goes(self, staged):
        """The client asks for the key's passphrase. The account password
        would be the wrong secret, exposed for nothing."""
        app, copied = staged
        app._stage_password_for_paste({
            "password": "accountpw", "ssh_key_source": "file",
            "ssh_key_path": "x", "ssh_key_passphrase": "keyphrase"})
        assert copied == ["keyphrase"]

    def test_a_key_with_no_passphrase_stages_nothing(self, staged):
        """Nothing will be asked for, so nothing should be on the
        clipboard -- least of all the account password."""
        app, copied = staged
        app._stage_password_for_paste({
            "password": "accountpw", "ssh_key_source": "stored",
            "ssh_key": "x", "ssh_key_passphrase": ""})
        assert copied == [], f"put {copied} on the clipboard for nothing"
