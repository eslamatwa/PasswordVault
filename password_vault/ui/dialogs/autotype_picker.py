"""A small list of passwords, opened by the shortcut.

This is deliberately *not* one of the app's modal dialogs. Those are
`transient` children with a grab, which is right for something opened
from inside the window and wrong here: the shortcut is pressed while the
user is in a browser or a terminal, and a transient child drags its owner
up with it — so asking for one password brought the whole vault to the
front. It reported as "it opens the whole program and that is not nice",
and it was.

So: a small always-on-top window of its own, no grab, Escape closes it.
The window that was in front is remembered before this opens, because
opening it takes the focus away, and nothing is typed until that window
has been confirmed back in front.
"""

from __future__ import annotations

import customtkinter as ctk

from ...autotype import candidates
from ...autotype_match import patterns_of, suggest_pattern
from ...autotype_sequence import describe
from ...i18n import anchor_start, pad, side_end, side_start, t
from ...theme import (
    ACCENT, ACCENT_HOVER, BG, BG_SEC, BG_TERT, GREEN, GREEN_HOVER,
    SEPARATOR, TEXT_ON_GREEN, TEXT_PRI, TEXT_SEC, TEXT_TERT, cat_emoji,
)
from ..widgets import dialog_header, tip

# Enough of the title to recognise the window, not so much that a long
# one pushes the list off the panel.
TITLE_SHOWN = 46

# Rows built up front. The rest arrive as soon as the user types — a
# large vault should not cost a visible pause on a shortcut press.
FIRST_PAGE = 25


def show(app, handle: int, window_title: str, which: str) -> None:
    offers = candidates(window_title, app.data.get("entries", []))

    panel = ctk.CTkToplevel(app.root)
    panel.title(t("Auto-Type"))
    panel.geometry("380x430")
    panel.minsize(320, 260)
    panel.configure(fg_color=BG)
    panel.attributes("-topmost", True)
    # No transient() and no grab_set(): both would tie this to the main
    # window and bring it forward.

    dialog_header(panel, t("⌨️  Auto-Type"), size=14, pady=(12, 2))

    shown = window_title if len(window_title) <= TITLE_SHOWN else (
        window_title[:TITLE_SHOWN] + "…")
    ctk.CTkLabel(
        panel, text=t("into: {window}", window=shown),
        font=ctk.CTkFont(size=10), text_color=TEXT_TERT,
        wraplength=340).pack(pady=(0, 2))

    # What "Type" is about to do. Without this the only way to find out
    # which shortcut was pressed is to press the button and watch.
    from ...autotype import PARTIAL

    plan = describe(PARTIAL[which]) if which in PARTIAL else None
    ctk.CTkLabel(
        panel,
        text=t("will type: {plan}",
               plan=plan or t("each entry's own order")),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        wraplength=340).pack(pady=(0, 6))

    search_var = ctk.StringVar()
    search = ctk.CTkEntry(
        panel, textvariable=search_var, height=32,
        font=ctk.CTkFont(size=12), fg_color=BG_SEC, border_width=0,
        corner_radius=8, text_color=TEXT_PRI,
        placeholder_text=t("Type to filter…"))
    search.pack(fill="x", padx=14, pady=(0, 6))

    scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent",
                                    scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    state = {"rows": [], "shown": []}

    # Matching reads the window title and nothing else, and some titles
    # simply do not mention the thing they belong to: an entry called
    # "wavz mail" at mail.wavz.com.eg cannot be connected to a window
    # called "Outlook - Google Chrome" by any amount of cleverness. This
    # is the way out -- pick once, tick this, and it matches from then on.
    suggestion = suggest_pattern(window_title)
    remember_var = ctk.BooleanVar(value=False)

    def remember(entry):
        if not (remember_var.get() and suggestion):
            return
        existing = patterns_of(entry)
        if suggestion.lower() in [p.lower() for p in existing]:
            return
        entry["match_patterns"] = "\n".join(existing + [suggestion])
        app._save_guarded()

    def close():
        try:
            panel.destroy()
        except Exception:  # noqa: BLE001 - already gone
            pass

    def type_it(entry):
        remember(entry)
        close()
        # Once this window is gone, not before: asking for the target
        # back while this one is still up just hands focus straight back.
        app.root.after(10, lambda: app.autotype.send(entry, handle, which))

    def copy_password(entry):
        remember(entry)
        close()
        app._copy_to_clipboard(entry.get("password", ""))

    def copy_username(entry):
        remember(entry)
        close()
        app._copy_to_clipboard(entry.get("username", ""))

    def build():
        for widget in state["rows"]:
            widget.destroy()
        state["rows"] = []
        needle = search_var.get().strip().lower()
        state["shown"] = []
        divided = False

        for entry, why in offers:
            haystack = " ".join((entry.get("title", ""),
                                 entry.get("username", ""),
                                 entry.get("url", ""))).lower()
            if needle and needle not in haystack:
                continue
            if not needle and len(state["shown"]) >= FIRST_PAGE:
                break
            state["shown"].append(entry)

            if not why and not divided and state["shown"][:-1]:
                # A quiet line between what was suggested and the rest of
                # the vault, so the suggestions still read as suggestions.
                divider = ctk.CTkLabel(
                    scroll, text=t("everything else"),
                    font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
                    anchor=anchor_start())
                divider.pack(fill="x", pady=(8, 2))
                state["rows"].append(divider)
                divided = True

            row = ctk.CTkFrame(scroll, fg_color=BG_SEC, corner_radius=8)
            row.pack(fill="x", pady=2)
            state["rows"].append(row)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=6)

            text_col = ctk.CTkFrame(inner, fg_color="transparent")
            text_col.pack(side=side_start(), fill="x", expand=True)
            ctk.CTkLabel(
                text_col,
                text=f"{cat_emoji(entry.get('category', ''))}  "
                     f"{entry.get('title', '')}",
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                 weight="bold"),
                text_color=TEXT_PRI, anchor=anchor_start()).pack(fill="x")
            detail = entry.get("username", "")
            subtitle = f"{detail}   ·   {why}" if (detail and why) else (
                why or detail)
            if subtitle:
                ctk.CTkLabel(
                    text_col, text=subtitle, font=ctk.CTkFont(size=10),
                    text_color=TEXT_SEC, anchor=anchor_start()).pack(
                    fill="x")

            type_btn = ctk.CTkButton(
                inner, text=t("Type"), width=50, height=28,
                font=ctk.CTkFont(size=11), fg_color=GREEN,
                hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
                corner_radius=6,
                command=lambda e=entry: type_it(e))
            type_btn.pack(side=side_end(), padx=pad(4, 0))
            tip(type_btn, t("Type it into the window behind this one"))

            # One button labelled "Copy" left the user asking which of
            # the two it copied. Two buttons, each saying so.
            pass_btn = ctk.CTkButton(
                inner, text="🔑", width=32, height=28,
                font=ctk.CTkFont(size=12), fg_color=ACCENT,
                hover_color=ACCENT_HOVER, corner_radius=6,
                command=lambda e=entry: copy_password(e))
            pass_btn.pack(side=side_end(), padx=pad(4, 0))
            tip(pass_btn, t("Copy the password"))

            user_btn = ctk.CTkButton(
                inner, text="👤", width=32, height=28,
                font=ctk.CTkFont(size=12), fg_color=BG_TERT,
                hover_color=SEPARATOR, text_color=TEXT_SEC,
                corner_radius=6,
                command=lambda e=entry: copy_username(e))
            user_btn.pack(side=side_end())
            tip(user_btn, t("Copy the username"))

        if not state["shown"]:
            empty = ctk.CTkLabel(
                scroll, text=t("Nothing matches that."),
                font=ctk.CTkFont(size=11), text_color=TEXT_SEC)
            empty.pack(pady=20)
            state["rows"].append(empty)

    def first(_event=None):
        if state["shown"]:
            type_it(state["shown"][0])

    search_var.trace_add("write", lambda *_a: build())
    panel.bind("<Return>", first)
    panel.bind("<Escape>", lambda _e: close())
    build()

    if suggestion:
        remember_box = ctk.CTkCheckBox(
            panel, text=t("Remember this window: {pattern}",
                          pattern=suggestion),
            variable=remember_var, font=ctk.CTkFont(size=10),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=4,
            border_width=2, text_color=TEXT_SEC, checkbox_width=16,
            checkbox_height=16)
        remember_box.pack(fill="x", padx=14, pady=(0, 4))
        tip(remember_box,
            t("Adds it to the entry's window patterns, so this window "
              "matches by itself next time."))

    ctk.CTkLabel(
        panel,
        text=t("Enter types the first one. Esc closes."),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT).pack(
        fill="x", padx=14, pady=(0, 10))

    panel.lift()
    panel.focus_force()
    search.focus_set()
