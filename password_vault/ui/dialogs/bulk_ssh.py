"""Open SSH sessions to several servers at once.

Opening ten machines one at a time means ten trips through the same
dialog, re-picking the same client and re-typing nothing that changed.

Servers come from the vault or are typed in, and typing is not a
fallback. One domain account often opens machines that are different
every time and were never worth storing individually — that is the case
the vault list cannot serve, and it is the case this feature is most
useful for. Parsing lives in `ui/bulk_targets.py`, away from the window,
because a misread line means a session opened to the wrong machine with a
domain account.

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
from ..bulk_targets import parse_hosts
from ..widgets import dialog_header, tip

log = logging.getLogger("PasswordVault")

# Above this many at once, ask first. Ten SSH sessions is a lot of
# processes to start from one click, and a mis-click on "select all" in a
# large vault should not be irreversible.
CONFIRM_ABOVE = 5

NO_CREDENTIAL = "—"


def collect_targets(app) -> list[dict]:
    """Every entry that plausibly describes a machine to log into."""
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


def credential_choices(app) -> list[tuple[str, dict | None]]:
    """Entries offered as the account for typed hosts.

    Every entry, not only the server-looking ones: the whole point of
    typing hosts is that the account is a domain login whose entry has no
    host of its own and never will.
    """
    choices: list[tuple[str, dict | None]] = [(NO_CREDENTIAL, None)]
    for entry in app.data.get("entries", []):
        title = entry.get("title", "") or t("(untitled)")
        user = entry.get("username", "")
        choices.append((f"{title} — {user}" if user else title, entry))
    return choices


def _label_of(target) -> str:
    """What to call this row.

    A typed host names itself. A vault entry is named by its title, which
    is what the user picked it by — and typed hosts sharing one credential
    entry would otherwise all show that entry's title.
    """
    if target.get("label"):
        return target["label"]
    entry = target.get("entry") or {}
    return entry.get("title", "")


def _describe(target) -> str:
    """user@host:port, leaving out the parts that carry no information."""
    text = target["host"]
    if target["user"]:
        text = f"{target['user']}@{text}"
    if target["port"] != 22:
        text = f"{text}:{target['port']}"
    return text


def show(app) -> None:
    dlg = app._make_dialog("Open Multiple SSH Sessions", 560, 640)
    dialog_header(dlg, t("🖥️  Open Multiple SSH Sessions"),
                  size=15, pady=(14, 2))

    clients = app._detect_ssh_clients(app.settings)
    subtitle = ctk.CTkLabel(
        dlg, text="", font=ctk.CTkFont(size=10), text_color=TEXT_TERT)
    subtitle.pack(pady=(0, 6))

    # ── Client, once for the whole batch ──
    top = ctk.CTkFrame(dlg, fg_color="transparent")
    top.pack(fill="x", padx=16, pady=(0, 4))
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

    FROM_VAULT = t("From the vault")
    TYPED = t("Type them in")
    tabs = ctk.CTkTabview(
        dlg, fg_color=BG_SEC, segmented_button_selected_color=ACCENT,
        segmented_button_selected_hover_color=ACCENT_HOVER,
        text_color=TEXT_PRI, height=330)
    tabs.pack(fill="both", expand=True, padx=12, pady=(4, 2))
    tabs.add(FROM_VAULT)
    tabs.add(TYPED)

    # ══ Tab 1: pick from the vault ══
    vault_tab = tabs.tab(FROM_VAULT)
    targets = collect_targets(app)
    picks: list[tuple[dict, ctk.BooleanVar]] = []

    if not targets:
        ctk.CTkLabel(
            vault_tab,
            text=t("Nothing in the vault looks like a server.\n\n"
                   "Give an entry a host or IP as its address, or a "
                   "server category — or type the servers in on the "
                   "other tab."),
            font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
            justify="center", wraplength=440).pack(expand=True, padx=20)
    else:
        scroll = ctk.CTkScrollableFrame(vault_tab, fg_color="transparent",
                                        scrollbar_button_color=BG_TERT)
        scroll.pack(fill="both", expand=True)

        for target in targets:
            entry = target["entry"]
            row = ctk.CTkFrame(scroll, fg_color=BG, corner_radius=8)
            row.pack(fill="x", pady=3)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=7)

            var = ctk.BooleanVar(value=not target["problem"])
            box = ctk.CTkCheckBox(
                inner, text="", width=24, checkbox_width=20,
                checkbox_height=20, fg_color=ACCENT,
                hover_color=ACCENT_HOVER, corner_radius=5,
                border_width=2, variable=var)
            box.pack(side=side_start())
            if target["problem"]:
                box.configure(state="disabled")

            text_col = ctk.CTkFrame(inner, fg_color="transparent")
            text_col.pack(side=side_start(), fill="x", expand=True,
                          padx=pad(8, 0))
            ctk.CTkLabel(
                text_col,
                text=f"{cat_emoji(entry.get('category', ''))}  "
                     f"{entry.get('title', '')}",
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                 weight="bold"),
                text_color=TEXT_PRI, anchor=anchor_start()).pack(fill="x")
            ctk.CTkLabel(
                text_col,
                text=(target["problem"] if target["problem"]
                      else _describe(target)),
                font=ctk.CTkFont(size=10),
                text_color=RED if target["problem"] else TEXT_SEC,
                anchor=anchor_start()).pack(fill="x")

            if not target["problem"]:
                picks.append((target, var))
                var.trace_add("write", lambda *_a: _refresh_count())

        tools = ctk.CTkFrame(vault_tab, fg_color="transparent")
        tools.pack(fill="x", pady=(4, 0))

        def _set_all(value):
            for _, var in picks:
                var.set(value)

        for label, value in ((t("Select all"), True),
                             (t("Select none"), False)):
            ctk.CTkButton(
                tools, text=label, width=90, height=28,
                font=ctk.CTkFont(size=11), fg_color=BG_TERT,
                hover_color=SEPARATOR, text_color=TEXT_SEC,
                corner_radius=6,
                command=lambda v=value: _set_all(v)).pack(
                side=side_start(), padx=pad(0, 6))

    # ══ Tab 2: type them in ══
    typed_tab = tabs.tab(TYPED)
    ctk.CTkLabel(
        typed_tab,
        text=t("One server per line:  host   or   user@host   or   "
               "user@host:port"),
        font=ctk.CTkFont(size=10), text_color=TEXT_TERT,
        anchor=anchor_start()).pack(fill="x", pady=(0, 4))

    hosts_box = ctk.CTkTextbox(
        typed_tab, height=170, font=ctk.CTkFont(family="Consolas", size=12),
        fg_color=BG, border_width=0, corner_radius=8, text_color=TEXT_PRI,
        wrap="none")
    hosts_box.pack(fill="both", expand=True)
    hosts_box.bind("<KeyRelease>", lambda _e: _refresh_count())

    cred_row = ctk.CTkFrame(typed_tab, fg_color="transparent")
    cred_row.pack(fill="x", pady=(6, 0))
    ctk.CTkLabel(cred_row, text=t("Account"),
                 font=ctk.CTkFont(family="Segoe UI", size=12),
                 text_color=TEXT_PRI).pack(side=side_start())
    choices = credential_choices(app)
    cred_var = ctk.StringVar(
        value=choices[1][0] if len(choices) > 1 else NO_CREDENTIAL)
    ctk.CTkComboBox(
        cred_row, values=[name for name, _ in choices], variable=cred_var,
        width=280, height=32, font=ctk.CTkFont(size=11), fg_color=BG,
        border_width=0, corner_radius=8, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, dropdown_fg_color=BG_SEC,
        dropdown_hover_color=ACCENT, text_color=TEXT_PRI,
        state="readonly", command=lambda _v: _refresh_count()).pack(
        side=side_end())
    ctk.CTkLabel(
        typed_tab,
        text=t("Its username fills in any line that does not name one, "
               "and its password is what the panel copies."),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        wraplength=480, anchor=anchor_start()).pack(fill="x", pady=(2, 0))

    err = ctk.CTkLabel(dlg, text="", text_color=RED,
                       font=ctk.CTkFont(size=10), height=14,
                       wraplength=500)
    err.pack(fill="x", padx=16)

    ctk.CTkLabel(
        dlg,
        text=t("💡 Passwords are not copied automatically — a panel opens "
               "with one button per server"),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        wraplength=500).pack(fill="x", padx=16, pady=(0, 4))

    def _credential():
        return next((e for name, e in choices if name == cred_var.get()),
                    None)

    def _typed_targets():
        """Parse the box, attaching the chosen account to each host."""
        entry = _credential()
        found, problems = parse_hosts(
            hosts_box.get("1.0", "end"),
            default_user=(entry or {}).get("username", ""),
            check=app._check_remote_arg)
        for target in found:
            target["entry"] = entry
        return found, problems

    def _current():
        if tabs.get() == TYPED:
            return _typed_targets()
        return [target for target, var in picks if var.get()], []

    def _refresh_count(*_args):
        chosen, problems = _current()
        if tabs.get() == TYPED:
            subtitle.configure(text=t("{n} servers typed", n=len(chosen)))
        else:
            subtitle.configure(
                text=t("{chosen} of {total} selected", chosen=len(chosen),
                       total=len(picks)))
        err.configure(text=problems[0] if problems else "")
        if chosen:
            go.configure(state="normal",
                         text=t("🖥️  Open {n} sessions", n=len(chosen)))
        else:
            go.configure(state="disabled", text=t("🖥️  Open sessions"))

    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(fill="x", padx=16, pady=(0, 14))
    ctk.CTkButton(
        btn_row, text=t("Cancel"), width=90, height=36,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=SEPARATOR, text_color=TEXT_SEC, corner_radius=8,
        command=dlg.destroy).pack(side=side_start())

    def launch():
        chosen, problems = _current()
        if problems:
            # Refused lines are reported, never skipped in silence: a
            # dropped server looks the same as one that failed to connect.
            err.configure(text="  •  ".join(problems[:3]))
            if not chosen:
                return
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
    tip(go, t("Start a session for every server listed"))

    # Switching tabs changes what "open" means, so the count has to follow.
    tabs.configure(command=_refresh_count)
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
        entry = target.get("entry")
        row = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=8)
        row.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side=side_start(), fill="x", expand=True)
        ctk.CTkLabel(
            text_col, text=_label_of(target),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRI, anchor=anchor_start()).pack(fill="x")
        ctk.CTkLabel(
            text_col, text=_describe(target), font=ctk.CTkFont(size=10),
            text_color=TEXT_SEC, anchor=anchor_start()).pack(fill="x")

        if entry:
            button = ctk.CTkButton(
                inner, text=t("🔑 Copy"), width=76, height=30,
                font=ctk.CTkFont(size=11), fg_color=ACCENT,
                hover_color=ACCENT_HOVER, corner_radius=7)
            button.pack(side=side_end())
            button.configure(
                command=lambda e=entry, b=button:
                    app._stage_password_for_paste(e, button=b))
        else:
            # Typed hosts with no account chosen. Showing a dead button
            # would suggest a password exists to copy.
            ctk.CTkLabel(
                inner, text=t("no account"), font=ctk.CTkFont(size=10),
                text_color=TEXT_TERT).pack(side=side_end())

    ctk.CTkButton(
        panel, text=t("Close"), height=32, font=ctk.CTkFont(size=12),
        fg_color=BG_TERT, hover_color=SEPARATOR, text_color=TEXT_SEC,
        corner_radius=8, command=panel.destroy).pack(
        fill="x", padx=16, pady=(0, 14))

    return panel
