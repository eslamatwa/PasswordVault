"""Security Dashboard — score + stats + HIBP breach check."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...i18n import (
    anchor_end, anchor_start, justify_start, side_end, side_start, t,
)
from ...security import calculate_security_score, check_hibp_batch
from ...settings import PASSWORD_AGE_WARNING
from ...theme import (
    BG_TERT, CARD_HOVER, GREEN, ORANGE, PURPLE, PURPLE_HOVER, RED, SEPARATOR,
    TEXT_PRI, TEXT_SEC,
)
from ..widgets import dialog_header, ios_group, tip

# Breached entries listed inline; the rest are summarised as a count.
MAX_LISTED_BREACHES = 15


def show(app) -> None:
    dlg = app._make_dialog("Security Dashboard", 480, 560)

    entries = app.data.get("entries", [])
    score, stats = calculate_security_score(entries)

    dialog_header(dlg, "Security Dashboard", icon="🛡️",
                  size=17, pady=(14, 8))

    score_color = GREEN if score >= 70 else (ORANGE if score >= 40
                                              else RED)
    sc_frame = ctk.CTkFrame(dlg, fg_color="transparent")
    sc_frame.pack(pady=(0, 8))
    ctk.CTkLabel(sc_frame,
                  text=f"🏆  {score}",
                  font=ctk.CTkFont(family="Segoe UI", size=44,
                                    weight="bold"),
                  text_color=score_color).pack(side="left")
    ctk.CTkLabel(sc_frame, text="/ 100",
                  font=ctk.CTkFont(size=16),
                  text_color=TEXT_SEC).pack(
        side="left", padx=(4, 0), pady=(14, 0))

    pb = ctk.CTkProgressBar(dlg, width=300, height=8, corner_radius=4,
                              fg_color=BG_TERT, progress_color=score_color)
    pb.pack(pady=(0, 14))
    pb.set(score / 100)
    tip(pb, t("Your security score: {score}/100", score=score))

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                     scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=14, pady=(0, 8))

    g = ios_group(scroll, "Overview")

    def stat_row(grp, icon, label, value, color, idx=0):
        if idx > 0:
            ctk.CTkFrame(grp, height=1,
                          fg_color=SEPARATOR).pack(
                fill="x", padx=(46, 0))
        row = ctk.CTkFrame(grp, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row, text=f"{icon}  {t(label)}",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_SEC,
                      anchor=anchor_start()).pack(side=side_start())
        ctk.CTkLabel(row, text=str(value),
                      font=ctk.CTkFont(family="Segoe UI", size=14,
                                        weight="bold"),
                      text_color=color,
                      anchor=anchor_end()).pack(side=side_end())

    stat_row(g, "📊", "Total Entries", stats["total"], TEXT_PRI, 0)
    stat_row(g, "💪", "Strong Passwords", stats["strong"], GREEN, 1)
    stat_row(g, "⚖️", "Fair Passwords", stats["fair"], ORANGE, 2)
    stat_row(g, "⚠️", "Weak Passwords", stats["weak"], RED, 3)
    stat_row(g, "🔁", "Duplicate Passwords",
              stats["duplicates"], ORANGE, 4)
    stat_row(g, "⏰", t("Old (>{days}d)", days=PASSWORD_AGE_WARNING),
              stats["old"], ORANGE, 5)

    recs = []
    if stats["weak"] > 0:
        recs.append(t(
            "⚠️  {count} weak password(s) — update them for better "
            "security", count=stats["weak"]))
    if stats["duplicates"] > 0:
        recs.append(t(
            "🔁  {count} reused password(s) — use unique passwords per "
            "account", count=stats["duplicates"]))
    if stats["old"] > 0:
        recs.append(t(
            "⏰  {count} password(s) older than {days} days — consider "
            "updating", count=stats["old"], days=PASSWORD_AGE_WARNING))
    if not recs:
        recs.append(t("✅  Great job! Your vault is secure!"))

    g2 = ios_group(scroll, "Recommendations")
    for i, rec in enumerate(recs):
        if i > 0:
            ctk.CTkFrame(g2, height=1,
                          fg_color=SEPARATOR).pack(
                fill="x", padx=(16, 0))
        ctk.CTkLabel(g2, text=rec,
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_PRI, anchor=anchor_start(),
                      wraplength=380, justify=justify_start()).pack(
            fill="x", padx=12, pady=5)

    g3 = ios_group(scroll, "Breach Check")
    breach_lbl = ctk.CTkLabel(
        g3,
        text=t("Check if your passwords appear in known\n"
             "data breaches (via Have I Been Pwned)."),
        font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
        justify="center")
    breach_lbl.pack(padx=12, pady=(8, 4))

    breach_result = ctk.CTkLabel(
        g3, text="", font=ctk.CTkFont(size=11),
        text_color=TEXT_PRI, wraplength=380, justify=justify_start())
    breach_result.pack(padx=12, pady=(0, 8))

    def start_breach():
        # Re-read the vault: it may have been edited since the dialog opened,
        # and checking a stale snapshot would report on entries that are
        # gone and miss the ones just added.
        current = list(app.data.get("entries", []))
        if not current:
            breach_result.configure(
                text=t("No entries to check."), text_color=TEXT_SEC)
            return
        breach_btn.configure(state="disabled", text=t("⏳ Checking..."))
        breach_result.configure(
            text=t("Checking passwords against HIBP database..."),
            text_color=TEXT_SEC)

        def _alive() -> bool:
            """The check runs in a worker; the dialog may already be gone."""
            try:
                return bool(dlg.winfo_exists())
            except tk.TclError:
                return False

        def on_progress(done, total):
            def _tick():
                if not _alive():
                    return
                breach_result.configure(
                    text=t("Checking passwords… {done}/{total}",
                           done=done, total=total),
                    text_color=TEXT_SEC)

            app.root.after(0, _tick)

        def on_done(results):
            def _update():
                if not _alive():
                    return
                breached = {eid: c for eid, c in results.items()
                            if c > 0}
                errors = sum(1 for c in results.values() if c < 0)
                if breached:
                    names = []
                    for e in current:
                        if e.get("id") in breached:
                            names.append(
                                f"  ⛔ {e.get('title', '?')} "
                                f"({breached[e['id']]:,}x)")
                    # One unbounded label broke the layout on a big vault.
                    listed = names[:MAX_LISTED_BREACHES]
                    if len(names) > MAX_LISTED_BREACHES:
                        listed.append(t(
                            "  … and {count} more",
                            count=len(names) - MAX_LISTED_BREACHES))
                    txt = (t("🚨 {count} password(s) found in "
                             "breaches!", count=len(breached))
                           + "\n" + "\n".join(listed))
                    breach_result.configure(text=txt, text_color=RED)
                else:
                    txt = t("✅ No passwords found in breaches!")
                    if errors:
                        txt += "\n" + t(
                            "⚠️ {count} could not be checked "
                            "(network error)", count=errors)
                    breach_result.configure(text=txt, text_color=GREEN)
                breach_btn.configure(state="normal",
                                      text=t("🔍  Check Breaches"))

            app.root.after(0, _update)

        check_hibp_batch(current, on_progress, on_done)

    breach_btn = ctk.CTkButton(
        g3, text=t("🔍  Check Breaches"), height=34,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=PURPLE, hover_color=PURPLE_HOVER,
        corner_radius=8, command=start_breach)
    breach_btn.pack(padx=12, pady=(0, 10))
    tip(breach_btn,
        t("Check all passwords against the HIBP breach database "
        "(uses k-anonymity — your passwords are NOT sent)"))

    ctk.CTkButton(
        dlg, text=t("Close"), height=36, width=140,
        font=ctk.CTkFont(size=13), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(pady=(0, 12))
