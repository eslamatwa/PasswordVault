"""Security Dashboard — score + stats + HIBP breach check."""

from __future__ import annotations

import customtkinter as ctk

from ...security import calculate_security_score, check_hibp_batch
from ...settings import PASSWORD_AGE_WARNING
from ...theme import (
    BG_TERT, CARD_HOVER, GREEN, ORANGE, PURPLE, RED, SEPARATOR,
    TEXT_PRI, TEXT_SEC,
)
from ..widgets import ios_group, tip


def show(app) -> None:
    dlg = app._make_dialog("Security Dashboard", 480, 560)

    entries = app.data.get("entries", [])
    score, stats = calculate_security_score(entries)

    ctk.CTkLabel(dlg, text="🛡️  Security Dashboard",
                  font=ctk.CTkFont(family="Segoe UI", size=17,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(14, 8))

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
    tip(pb, f"Your security score: {score}/100")

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
        ctk.CTkLabel(row, text=f"{icon}  {label}",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_SEC, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=str(value),
                      font=ctk.CTkFont(family="Segoe UI", size=14,
                                        weight="bold"),
                      text_color=color, anchor="e").pack(side="right")

    stat_row(g, "📊", "Total Entries", stats["total"], TEXT_PRI, 0)
    stat_row(g, "💪", "Strong Passwords", stats["strong"], GREEN, 1)
    stat_row(g, "⚖️", "Fair Passwords", stats["fair"], ORANGE, 2)
    stat_row(g, "⚠️", "Weak Passwords", stats["weak"], RED, 3)
    stat_row(g, "🔁", "Duplicate Passwords",
              stats["duplicates"], ORANGE, 4)
    stat_row(g, "⏰", f"Old (>{PASSWORD_AGE_WARNING}d)",
              stats["old"], ORANGE, 5)

    recs = []
    if stats["weak"] > 0:
        recs.append(
            f"⚠️  {stats['weak']} weak password(s) — "
            f"update them for better security")
    if stats["duplicates"] > 0:
        recs.append(
            f"🔁  {stats['duplicates']} reused password(s) — "
            f"use unique passwords per account")
    if stats["old"] > 0:
        recs.append(
            f"⏰  {stats['old']} password(s) older than "
            f"{PASSWORD_AGE_WARNING} days — consider updating")
    if not recs:
        recs.append("✅  Great job! Your vault is secure!")

    g2 = ios_group(scroll, "Recommendations")
    for i, rec in enumerate(recs):
        if i > 0:
            ctk.CTkFrame(g2, height=1,
                          fg_color=SEPARATOR).pack(
                fill="x", padx=(16, 0))
        ctk.CTkLabel(g2, text=rec,
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_PRI, anchor="w",
                      wraplength=380, justify="left").pack(
            fill="x", padx=12, pady=5)

    g3 = ios_group(scroll, "Breach Check")
    breach_lbl = ctk.CTkLabel(
        g3,
        text="Check if your passwords appear in known\n"
             "data breaches (via Have I Been Pwned).",
        font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
        justify="center")
    breach_lbl.pack(padx=12, pady=(8, 4))

    breach_result = ctk.CTkLabel(
        g3, text="", font=ctk.CTkFont(size=11),
        text_color=TEXT_PRI, wraplength=380, justify="left")
    breach_result.pack(padx=12, pady=(0, 8))

    def start_breach():
        if not entries:
            breach_result.configure(
                text="No entries to check.", text_color=TEXT_SEC)
            return
        breach_btn.configure(state="disabled", text="⏳ Checking...")
        breach_result.configure(
            text="Checking passwords against HIBP database...",
            text_color=TEXT_SEC)

        def on_done(results):
            def _update():
                breached = {eid: c for eid, c in results.items()
                            if c > 0}
                errors = sum(1 for c in results.values() if c < 0)
                if breached:
                    names = []
                    for e in entries:
                        if e.get("id") in breached:
                            names.append(
                                f"  ⛔ {e.get('title', '?')} "
                                f"({breached[e['id']]:,}x)")
                    txt = (f"🚨 {len(breached)} password(s) "
                           f"found in breaches!\n"
                           + "\n".join(names))
                    breach_result.configure(text=txt, text_color=RED)
                else:
                    txt = "✅ No passwords found in breaches!"
                    if errors:
                        txt += (f"\n⚠️ {errors} could not "
                                f"be checked (network error)")
                    breach_result.configure(text=txt, text_color=GREEN)
                breach_btn.configure(state="normal",
                                      text="🔍  Check Breaches")

            app.root.after(0, _update)

        check_hibp_batch(entries, None, on_done)

    breach_btn = ctk.CTkButton(
        g3, text="🔍  Check Breaches", height=34,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=PURPLE, hover_color="#a04ad0",
        corner_radius=8, command=start_breach)
    breach_btn.pack(padx=12, pady=(0, 10))
    tip(breach_btn,
        "Check all passwords against the HIBP breach database "
        "(uses k-anonymity — your passwords are NOT sent)")

    ctk.CTkButton(
        dlg, text="Close", height=36, width=140,
        font=ctk.CTkFont(size=13), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(pady=(0, 12))
