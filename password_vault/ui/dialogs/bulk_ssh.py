"""Open SSH sessions to several servers at once.

Opening ten machines one at a time means ten trips through the same
dialog, re-picking the same client and re-typing nothing that changed.
This lists everything in the vault that looks like a machine to log into
and opens the ones that are ticked.

The hard part is not the launching, it is the password. The single
session flow puts one password on the clipboard for the user to paste;
ten sessions cannot put ten there, and rotating through them on a timer
would mean the clipboard holding whichever secret happened to be current
when the user pressed Ctrl+V. So nothing is staged automatically here.
The sessions open, and a small panel stays up with one button per server:
the user clicks the row for the tab they are looking at, and that one
password goes to the clipboard under the usual auto-clear. One secret is
exposed at a time, and it is the one that was asked for.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from ...i18n import anchor_start, pad, side_end, side_start, t
from ...theme import (
    ACCENT, ACCENT_HOVER, BG, BG_SEC, BG_TERT, GREEN, GREEN_HOVER, RED,
    SEPARATOR, TEXT_ON_GREEN, TEXT_PRI, TEXT_SEC, TEXT_TERT, cat_emoji,
)
from ..widgets import dialog_header, tip

log = logging.getLogger("PasswordVault")

# Gap between launches. Starting ten clients in the same instant makes a
# cold-starting MobaXterm drop tabs, and it hands the machine a thundering
# herd of processes for no benefit -- the user cannot read ten terminals
# at once anyway.
LAUNCH_STAGGER_MS = 400

# Above this many at once, ask first. Ten SSH sessions is a lot of
# processes to start from one click, and a mis-click on "select all" in a
# large vault should not be irreversible.
CONFIRM_ABOVE = 5


def collect_targets(app) -> list[dict]:
    """Every entry that plausibly describes a machine to log into.

    Reuses the same test as the right-click menu, so an entry that offers
    "SSH Session ..." individually is exactly one that appears here.
    """
    targets = []
    for entry in app.data.get("entries", []):
        url = entry.get("url", "") or ""
        if not app._looks_remote(entry, url):
            continue
        host = app._extract_host(url, entry)
        if not host:
            # Nothing to connect to. Silently skipping would be confusing
            # in a list the user expects to mirror the menu, so these are
            # shown as unpickable rather than hidden.
            targets.append({"entry": entry, "host": "", "user": "",
                            "port": 22, "problem": t("no host or IP")})
            continue
        user = entry.get("username", "") or ""
        port = app._extract_port(url, 22)
        problem = (app._check_remote_arg(host, t("Host / IP"))
                   or app._check_remote_arg(user, t("Username")))
        targets.append({"entry": entry, "host": host, "user": user,
                        "port": port, "problem": problem})
    targets.sort(key=lambda item: item["entry"].get("title", "").lower())
    return targets


def _describe(target) -> str:
    """user@host:port, leaving out the parts that carry no information."""
    text = target["host"]
    if target["user"]:
        text = f"{target['user']}@{text}"
    if target["port"] != 22:
        text = f"{text}:{target['port']}"
    return text


def show(app) -> None:
    targets = collect_targets(app)
    dlg = app._make_dialog("Open Multiple SSH Sessions", 520, 560)

    dialog_header(dlg, t("🖥️  Open Multiple SSH Sessions"),
                  size=15, pady=(14, 2))

    if not targets:
        ctk.CTkLabel(
            dlg,
            text=t("No entries look like a server.\n\nAn entry qualifies "
                   "when its category is a server one, or its address is "
                   "a bare host, an IP, or an ssh:// address."),
            font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
            justify="center", wraplength=440).pack(
            expand=True, padx=24, pady=20)
        ctk.CTkButton(
            dlg, text=t("Close"), width=110, height=36,
            font=ctk.CTkFont(size=12), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
            command=dlg.destroy).pack(pady=(0, 16))
        return

    clients = app._detect_ssh_clients()
    subtitle = ctk.CTkLabel(
        dlg, text="", font=ctk.CTkFont(size=10), text_color=TEXT_TERT)
    subtitle.pack(pady=(0, 8))

    # ── Client, once for the whole batch ──
    top = ctk.CTkFrame(dlg, fg_color="transparent")
    top.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(top, text=t("SSH Client"),
                 font=ctk.CTkFont(family="Segoe UI", size=12),
                 text_color=TEXT_PRI).pack(side=side_start())
    client_names = ([c[0] for c in clients] if clients
                    else [t("No SSH client found")])
    client_var = ctk.StringVar(value=client_names[0])
    ctk.CTkComboBox(
        top, values=client_names, variable=client_var, width=200,
        height=32, font=ctk.CTkFont(size=12), fg_color=BG_SEC,
        border_width=0, corner_radius=8, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, dropdown_fg_color=BG_SEC,
        dropdown_hover_color=ACCENT, text_color=TEXT_PRI,
        state="readonly").pack(side=side_end())

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                    scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=12, pady=(4, 4))

    picks: list[tuple[dict, ctk.BooleanVar]] = []

    def _refresh_count(*_args):
        chosen = sum(1 for _, var in picks if var.get())
        subtitle.configure(
            text=t("{chosen} of {total} selected", chosen=chosen,
                   total=len(picks)))
        if chosen:
            go.configure(state="normal",
                         text=t("🖥️  Open {n} sessions", n=chosen))
        else:
            go.configure(state="disabled", text=t("🖥️  Open sessions"))

    for target in targets:
        entry = target["entry"]
        row = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=8)
        row.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)

        var = ctk.BooleanVar(value=not target["problem"])
        box = ctk.CTkCheckBox(
            inner, text="", width=24, checkbox_width=20, checkbox_height=20,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=5,
            border_width=2, variable=var, command=_refresh_count)
        box.pack(side=side_start())
        if target["problem"]:
            # Cannot be launched, so it cannot be selected. The reason is
            # shown rather than the row being dropped, because an entry
            # that offers SSH from its own menu and is missing here would
            # look like a bug in the list.
            box.configure(state="disabled")

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side=side_start(), fill="x", expand=True,
                      padx=pad(8, 0))
        ctk.CTkLabel(
            text_col,
            text=f"{cat_emoji(entry.get('category', ''))}  "
                 f"{entry.get('title', '')}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRI, anchor=anchor_start()).pack(
            fill="x")
        detail = (target["problem"] if target["problem"]
                  else _describe(target))
        ctk.CTkLabel(
            text_col, text=detail, font=ctk.CTkFont(size=10),
            text_color=RED if target["problem"] else TEXT_SEC,
            anchor=anchor_start()).pack(fill="x")

        if not target["problem"]:
            picks.append((target, var))
            var.trace_add("write", _refresh_count)

    # ── Select all / none ──
    tools = ctk.CTkFrame(dlg, fg_color="transparent")
    tools.pack(fill="x", padx=16, pady=(0, 4))

    def _set_all(value):
        for _, var in picks:
            var.set(value)
        _refresh_count()

    for label, value in ((t("Select all"), True), (t("Select none"), False)):
        ctk.CTkButton(
            tools, text=label, width=90, height=28,
            font=ctk.CTkFont(size=11), fg_color=BG_TERT,
            hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=6,
            command=lambda v=value: _set_all(v)).pack(
            side=side_start(), padx=pad(0, 6))

    err = ctk.CTkLabel(dlg, text="", text_color=RED,
                       font=ctk.CTkFont(size=10), height=14)
    err.pack(fill="x", padx=16)

    ctk.CTkLabel(
        dlg,
        text=t("💡 Passwords are not copied automatically — a panel opens "
               "with one button per server"),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        wraplength=470).pack(fill="x", padx=16, pady=(0, 4))

    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(fill="x", padx=16, pady=(0, 14))
    ctk.CTkButton(
        btn_row, text=t("Cancel"), width=90, height=36,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
        command=dlg.destroy).pack(side=side_start())

    def launch():
        chosen = [target for target, var in picks if var.get()]
        if not chosen:
            err.configure(text=t("⚠️ Nothing selected"))
            return
        if not clients:
            err.configure(text=t("⚠️ No SSH client found on system"))
            return
        name = client_var.get()
        path = next((p for n, p in clients if n == name), "")
        if not path:
            err.configure(text=t("⚠️ SSH client not found"))
            return

        def go_ahead(_dlg=None):
            dlg.destroy()
            app.launch_ssh_batch(chosen, name, path)

        if len(chosen) > CONFIRM_ABOVE:
            app._confirm(
                t("Open {n} SSH sessions?", n=len(chosen)),
                t("This starts {n} separate connections at once.",
                  n=len(chosen)),
                icon="🖥️", confirm_text=t("Open them"),
                on_confirm=go_ahead,
                window_title=t("Open Multiple SSH Sessions"))
        else:
            go_ahead()

    go = ctk.CTkButton(
        btn_row, text=t("🖥️  Open sessions"), height=36,
        font=ctk.CTkFont(size=13, weight="bold"), fg_color=GREEN,
        hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
        corner_radius=8, command=launch)
    go.pack(side=side_end(), fill="x", expand=True, padx=pad(8, 0))
    tip(go, t("Start a session for every ticked server"))

    _refresh_count()


def show_password_panel(app, launched: list[dict]) -> ctk.CTkToplevel:
    """A non-modal list of the open sessions, one copy button each.

    Deliberately not modal and deliberately on top: the user is about to
    be working in a terminal, and the whole point is to reach this while
    that terminal has focus.
    """
    panel = ctk.CTkToplevel(app.root)
    panel.title(t("Session Passwords"))
    panel.geometry("340x420")
    panel.minsize(300, 240)
    panel.configure(fg_color=BG)
    panel.attributes("-topmost", True)

    dialog_header(panel, t("🔑  Session Passwords"), size=14, pady=(12, 2))
    ctk.CTkLabel(
        panel,
        text=t("Click the server you are pasting into. One password goes "
               "to the clipboard at a time, and clears as usual."),
        font=ctk.CTkFont(size=10), text_color=TEXT_TERT,
        wraplength=300, justify="center").pack(padx=16, pady=(0, 8))

    scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent",
                                    scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    for target in launched:
        entry = target["entry"]
        row = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=8)
        row.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side=side_start(), fill="x", expand=True)
        ctk.CTkLabel(
            text_col, text=entry.get("title", ""),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRI, anchor=anchor_start()).pack(fill="x")
        ctk.CTkLabel(
            text_col, text=_describe(target), font=ctk.CTkFont(size=10),
            text_color=TEXT_SEC, anchor=anchor_start()).pack(fill="x")

        button = ctk.CTkButton(
            inner, text=t("🔑 Copy"), width=76, height=30,
            font=ctk.CTkFont(size=11), fg_color=ACCENT,
            hover_color=ACCENT_HOVER, corner_radius=7)
        button.pack(side=side_end())
        button.configure(
            command=lambda e=entry, b=button: app._stage_password_for_paste(
                e, button=b))

    ctk.CTkButton(
        panel, text=t("Close"), height=32, font=ctk.CTkFont(size=12),
        fg_color=BG_TERT, hover_color=SEPARATOR, text_color=TEXT_SEC,
        corner_radius=8, command=panel.destroy).pack(
        fill="x", padx=16, pady=(0, 14))

    return panel
