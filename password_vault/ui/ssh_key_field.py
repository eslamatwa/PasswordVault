"""The SSH key part of an entry: none, a file on disk, or one we hold.

Two decisions shape this.

**The passphrase box appears only when the key actually has a
passphrase.** Asking for one on a key that has none teaches people to
type their account password into a field nothing will ever read; staying
silent on a key that has one leaves them at a client prompt with an empty
clipboard. The answer comes from `sshkeys.describe`, which parses the key
body — `ssh-keygen` writes the same header either way, so there is no
shortcut.

**A generated key is stored; a key you already have is referenced.**
Storing puts the private key inside the encrypted vault, which is the
right place for a secret this app created. Referencing leaves a key the
user already manages where they put it, and this app never copies it.
They are different situations rather than a compromise.

This is dialog code. It uses CustomTkinter freely because it is built
once when the entry dialog opens — the entry cards are the hot path and
stay on plain Tk widgets.
"""

from __future__ import annotations

import logging
import os
from tkinter import filedialog

import customtkinter as ctk

from .. import sshkeys
from ..i18n import anchor_start, pad, side_end, side_start, t
from ..theme import (
    ACCENT, ACCENT_HOVER, BG_TERT, GREEN, INPUT_BG, RED, SEPARATOR,
    TEXT_PRI, TEXT_SEC, TEXT_TERT,
)
from .widgets import tip

log = logging.getLogger("PasswordVault")

NONE = "none"
FILE = "file"
STORED = "stored"

def source_labels():
    """The three choices, translated when asked for rather than at import.

    Written as literal `t()` calls rather than a table walked with
    `t(label)`: the coverage test reads the source to find what reaches
    the translator, and a variable tells it nothing. That is not the test
    being awkward — a string it cannot see is a string that can ship
    untranslated.
    """
    return {NONE: t("No key — password only"),
            FILE: t("A key file on this machine"),
            STORED: t("A key kept in the vault")}


def ssh_key_section(app, group, source, path, stored, entry_title):
    """Build the key controls. Returns ``{"read": callable}``.

    ``read()`` gives ``(source, path, stored_key, problem)``; a non-empty
    problem means the entry must not be saved, and is shown by the
    caller rather than raised — the same way a bad typing order is.
    """
    state = {"source": source or NONE, "stored": stored or "",
             "described": {}}

    ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
        fill="x", padx=(46, 0))

    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(6, 2))
    ctk.CTkLabel(row, text=t("SSH key"),
                 font=ctk.CTkFont(family="Segoe UI", size=12),
                 text_color=TEXT_PRI, width=72,
                 anchor=anchor_start()).pack(side=side_start())

    labels = source_labels()
    reverse = {v: k for k, v in labels.items()}
    source_var = ctk.StringVar(value=labels.get(state["source"],
                                                labels[NONE]))
    ctk.CTkComboBox(
        row, values=list(labels.values()), variable=source_var,
        height=30, font=ctk.CTkFont(size=11), fg_color=INPUT_BG,
        border_width=0, corner_radius=7, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, dropdown_fg_color=INPUT_BG,
        dropdown_hover_color=ACCENT, text_color=TEXT_PRI,
        state="readonly",
        command=lambda _v: _switch()).pack(
        side=side_start(), fill="x", expand=True, padx=pad(8, 0))

    # ── the file case ──
    file_box = ctk.CTkFrame(group, fg_color="transparent")
    path_row = ctk.CTkFrame(file_box, fg_color="transparent")
    path_row.pack(fill="x", padx=12, pady=(2, 2))
    path_var = ctk.StringVar(value=path or "")
    path_entry = ctk.CTkEntry(
        path_row, textvariable=path_var, height=30,
        font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0,
        corner_radius=7, text_color=TEXT_PRI, justify="left",
        placeholder_text=t("path to the private key"))
    path_entry.pack(side=side_start(), fill="x", expand=True)

    def browse():
        chosen = filedialog.askopenfilename(
            parent=group.winfo_toplevel(),
            title=t("Choose a private key"),
            initialdir=os.path.expanduser("~/.ssh"))
        if chosen:
            path_var.set(chosen)
            _inspect()

    browse_btn = ctk.CTkButton(
        path_row, text=t("Browse…"), width=72, height=30,
        font=ctk.CTkFont(size=11), fg_color=BG_TERT,
        hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=7,
        command=browse)
    browse_btn.pack(side=side_end(), padx=pad(6, 0))

    # ── the stored case ──
    stored_box = ctk.CTkFrame(group, fg_color="transparent")
    stored_row = ctk.CTkFrame(stored_box, fg_color="transparent")
    stored_row.pack(fill="x", padx=12, pady=(2, 2))
    stored_state = ctk.CTkLabel(
        stored_row, text="", font=ctk.CTkFont(size=11),
        text_color=TEXT_SEC, anchor=anchor_start())
    stored_state.pack(side=side_start(), fill="x", expand=True)

    def generate():
        def go(_dlg=None):
            try:
                private, public = sshkeys.generate(
                    "ed25519", comment=entry_title or "PasswordVault")
            except Exception as exc:  # noqa: BLE001 - report, never crash
                log.exception("SSH key generation failed.")
                _say(str(exc), RED)
                return
            state["stored"] = private
            _inspect()
            _show_public(public)

        if state["stored"]:
            # Replacing a stored key locks you out of every server that
            # trusts the old one, and there is no undo once saved.
            app._confirm(
                t("Replace the stored key?"),
                t("The key already in this entry is discarded. Any server "
                  "that trusts it will stop accepting this entry until "
                  "you install the new public key there."),
                icon="🔑", confirm_text=t("Replace it"), on_confirm=go,
                window_title=t("Replace the stored key?"))
        else:
            go()

    gen_btn = ctk.CTkButton(
        stored_row, text=t("Generate"), width=84, height=30,
        font=ctk.CTkFont(size=11), fg_color=GREEN,
        hover_color=ACCENT_HOVER, corner_radius=7, command=generate)
    gen_btn.pack(side=side_end(), padx=pad(6, 0))

    def show_public():
        if not state["stored"]:
            return
        try:
            public = sshkeys.public_from_private(
                state["stored"], entry_title or "PasswordVault")
        except sshkeys.KeyError_ as exc:
            _say(str(exc), RED)
            return
        _show_public(public)

    public_btn = ctk.CTkButton(
        stored_row, text=t("Public key"), width=90, height=30,
        font=ctk.CTkFont(size=11), fg_color=BG_TERT,
        hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=7,
        command=show_public)
    public_btn.pack(side=side_end())
    tip(public_btn, t("The half that goes on the server"))

    def _show_public(public):
        """A copyable box — a public key is useless to read aloud."""
        dlg = app._make_dialog("Public key", 460, 260)
        ctk.CTkLabel(
            dlg, text=t("🔑  Public key"),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRI).pack(pady=(14, 2))
        ctk.CTkLabel(
            dlg,
            text=t("Add this line to ~/.ssh/authorized_keys on the "
                   "server. It is not a secret."),
            font=ctk.CTkFont(size=10), text_color=TEXT_TERT,
            wraplength=410).pack(padx=20, pady=(0, 8))
        box = ctk.CTkTextbox(dlg, height=90, font=ctk.CTkFont(
            family="Consolas", size=10), fg_color=INPUT_BG,
            border_width=0, corner_radius=8, wrap="char")
        box.pack(fill="both", expand=True, padx=16)
        box.insert("1.0", public)
        row2 = ctk.CTkFrame(dlg, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(
            row2, text=t("Close"), width=90, height=32,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
            command=dlg.destroy).pack(side=side_start())
        ctk.CTkButton(
            row2, text=t("📋  Copy"), height=32,
            font=ctk.CTkFont(size=12), fg_color=ACCENT,
            hover_color=ACCENT_HOVER, corner_radius=8,
            command=lambda: app._copy_to_clipboard(public)).pack(
            side=side_end(), fill="x", expand=True, padx=pad(8, 0))

    # ── what the key turned out to be ──
    status = ctk.CTkLabel(
        group, text="", font=ctk.CTkFont(size=10), text_color=TEXT_TERT,
        anchor=anchor_start(), wraplength=340)
    status.pack(fill="x", padx=(58, 12), pady=(0, 2))

    def _say(text, colour=TEXT_TERT):
        status.configure(text=text, text_color=colour)

    # ── the passphrase, shown only when there is one ──
    pass_box = ctk.CTkFrame(group, fg_color="transparent")
    pass_row = ctk.CTkFrame(pass_box, fg_color="transparent")
    pass_row.pack(fill="x", padx=12, pady=(2, 6))
    ctk.CTkLabel(pass_row, text=t("Passphrase"),
                 font=ctk.CTkFont(family="Segoe UI", size=12),
                 text_color=TEXT_PRI, width=72,
                 anchor=anchor_start()).pack(side=side_start())
    pass_var = ctk.StringVar(value="")
    pass_entry = ctk.CTkEntry(
        pass_row, textvariable=pass_var, height=30, show="•",
        font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0,
        corner_radius=7, text_color=TEXT_PRI)
    pass_entry.pack(side=side_start(), fill="x", expand=True,
                    padx=pad(8, 0))
    tip(pass_entry,
        t("Copied to the clipboard when you connect, instead of the "
          "password."))

    def _inspect():
        """Look at whichever key is selected and report what it is."""
        state["described"] = {}
        if state["source"] == FILE:
            target = path_var.get().strip()
            if not target:
                _say(t("Choose the private key file — the one without "
                       ".pub"))
                _passphrase_visible(False)
                return
            found = sshkeys.read(target)
        elif state["source"] == STORED:
            if not state["stored"]:
                _say(t("No key yet. Generate one, and put its public "
                       "half on the server."))
                _passphrase_visible(False)
                return
            found = sshkeys.describe(state["stored"])
        else:
            _say("")
            _passphrase_visible(False)
            return

        state["described"] = found
        if found["problem"]:
            _say(found["problem"], RED)
            # `encrypted` is None here: not knowing is not the same as
            # knowing there is no passphrase, so the box is offered
            # rather than hidden.
            _passphrase_visible(found["encrypted"] is not False)
            return

        encrypted = found["encrypted"]
        kind = found["kind"]
        if encrypted:
            _say(t("{kind} key, protected by a passphrase", kind=kind))
        else:
            _say(t("{kind} key, no passphrase", kind=kind))
        _passphrase_visible(bool(encrypted))

    def _passphrase_visible(show):
        if show:
            pass_box.pack(fill="x")
        else:
            pass_box.pack_forget()
            pass_var.set("")

    def _switch():
        state["source"] = reverse.get(source_var.get(), NONE)
        file_box.pack_forget()
        stored_box.pack_forget()
        if state["source"] == FILE:
            file_box.pack(fill="x")
        elif state["source"] == STORED:
            stored_box.pack(fill="x")
            stored_state.configure(
                text=t("A key is stored in this entry")
                if state["stored"] else t("Nothing stored yet"))
        _inspect()

    path_entry.bind("<FocusOut>", lambda _e: _inspect(), add="+")
    path_entry.bind("<Return>", lambda _e: _inspect(), add="+")
    _switch()

    def read():
        source_now = state["source"]
        if source_now == NONE:
            return NONE, "", "", ""
        if source_now == FILE:
            target = path_var.get().strip()
            if not target:
                return NONE, "", "", t("choose a key file, or pick "
                                       "\"No key\"")
            if not os.path.isfile(target):
                return NONE, "", "", t("that file does not exist")
            found = sshkeys.read(target)
            if found["problem"] and found["kind"] == sshkeys.UNKNOWN:
                return NONE, "", "", found["problem"]
            return FILE, target, "", ""
        if not state["stored"]:
            return NONE, "", "", t("generate a key, or pick \"No key\"")
        return STORED, "", state["stored"], ""

    return {"read": read, "passphrase": lambda: pass_var.get(),
            "inspect": _inspect}
