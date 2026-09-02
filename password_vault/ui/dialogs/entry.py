"""The Add / Edit Password dialog.

Four fields nearly every entry uses, and an Advanced section holding the
per-entry machinery most of them never do: auto-type matching for one, an
SSH key for another. Collapsed, with the header naming what is set inside
-- hidden is fine, silently in force is not.
"""

from __future__ import annotations

import datetime
import uuid

import customtkinter as ctk

from ... import autotype_sequence
from ...autotype_sequence import DEFAULT as AUTOTYPE_DEFAULT
from ...i18n import anchor_start, pad, side_end, side_start, t
from ...security import password_hash, password_strength
from ...theme import (
    ACCENT, ACCENT_HOVER, BG_TERT, CARD_COLORS, GREEN, GREEN_HOVER,
    INPUT_BG, ORANGE, RED, SEPARATOR, TEXT_ON_ACCENT, TEXT_ON_GREEN,
    TEXT_PRI, TEXT_QUAT, TEXT_SEC, TEXT_TERT,
)
from ..ssh_key_field import ssh_key_section
from ..widgets import (
    collapsible_group, dialog_header, ios_combo, ios_field, ios_group, tip,
)


def show(app, entry=None):
    is_edit = entry is not None
    dlg = app._make_dialog(
        "Edit Password" if is_edit else "New Password", 420, 540)

    dialog_header(
        dlg, "Edit Password" if is_edit else "New Password",
        icon="✏️" if is_edit else "＋", size=14,
        pady=(8, 4))

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                     scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=12, pady=(0, 0))

    # IDENTITY
    # Shared with the category callback below, which runs before the
    # Advanced section is built if the user is quick.
    advanced = {"group": None, "nudged": False}

    g1 = ios_group(scroll, "Identity", compact=True)
    title_val = entry.get("title", "") if is_edit else ""
    title_e = ios_field(g1, "Title", idx=0, value=title_val,
                         height=30)
    cats = app.data.get("categories", ["General"])

    cat_val = (entry.get("category", cats[0] if cats else "")
               if is_edit else (cats[0] if cats else ""))
    # Picking a server category is the moment someone is thinking
    # about a machine, so that is where the key fields should turn
    # up -- rather than waiting to be found under Advanced by
    # somebody who does not know they exist.
    #
    # Only on a change the user makes, and only once: reopening a
    # section they deliberately collapsed would be the app arguing
    # with them.
    def _category_chosen(value):
        if not app._server_category(value):
            return
        if advanced["nudged"]:
            return
        advanced["nudged"] = True
        group = advanced.get("group")
        if group is not None:
            group.open_it()

    cat_cb = ios_combo(g1, "Category", cats, cat_val, idx=1,
                       command=_category_chosen)
    url_val = entry.get("url", "") if is_edit else ""
    url_e = ios_field(g1, "URL", idx=2, value=url_val, ltr=True,
                       height=30, placeholder="https://example.com")

    # CREDENTIALS
    g2 = ios_group(scroll, "Credentials", compact=True)
    user_val = entry.get("username", "") if is_edit else ""
    user_e = ios_field(g2, "Username", idx=0, value=user_val,
                        height=30)

    ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
        fill="x", padx=(46, 0))
    pw_row = ctk.CTkFrame(g2, fg_color="transparent")
    pw_row.pack(fill="x", padx=12, pady=(2, 3))
    ctk.CTkLabel(pw_row, text=t("Password"),
                  font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72,
                  anchor=anchor_start()).pack(side=side_start())
    pass_e = ctk.CTkEntry(
        pw_row, height=30, show="●",
        font=ctk.CTkFont(family="Segoe UI", size=12),
        fg_color=INPUT_BG, border_width=0, corner_radius=6,
        text_color=TEXT_PRI)
    pass_e.pack(side=side_start(), fill="x", expand=True, padx=4)
    if is_edit:
        pass_e.insert(0, entry.get("password", ""))
    gen_btn = ctk.CTkButton(
        pw_row, text="🎲", width=28, height=28,
        font=ctk.CTkFont(size=13),
        fg_color=GREEN, hover_color=GREEN_HOVER, corner_radius=6,
        text_color=TEXT_ON_GREEN,
        command=lambda: app._show_generator(pass_e))
    gen_btn.pack(side=side_end())
    tip(gen_btn, t("Open password generator"))

    def toggle_pass():
        if pass_e.cget("show") == "●":
            pass_e.configure(show="")
            eye_btn.configure(text="🙈")
        else:
            pass_e.configure(show="●")
            eye_btn.configure(text="👁")

    eye_btn = ctk.CTkButton(
        pw_row, text="👁", width=28, height=28,
        font=ctk.CTkFont(size=12), fg_color="transparent",
        hover_color=BG_TERT, corner_radius=6,
        text_color=TEXT_SEC, command=toggle_pass)
    eye_btn.pack(side=side_end(), padx=pad(0, 2))
    tip(eye_btn, t("Show / hide password"))

    # Strength bar
    sf = ctk.CTkFrame(scroll, fg_color="transparent")
    sf.pack(fill="x", padx=26, pady=(0, 2))
    str_bar = ctk.CTkProgressBar(
        sf, height=3, corner_radius=2,
        fg_color=BG_TERT, progress_color=TEXT_QUAT)
    str_bar.pack(side=side_start(), fill="x", expand=True)
    str_bar.set(0)
    str_lbl = ctk.CTkLabel(sf, text="",
                            font=ctk.CTkFont(size=9),
                            text_color=TEXT_QUAT)
    str_lbl.pack(side=side_start(), padx=pad(6, 0))
    tip(str_bar, t("Password strength indicator"))

    # Duplicate warning label
    dup_lbl = ctk.CTkLabel(scroll, text="",
                            font=ctk.CTkFont(size=9),
                            text_color=ORANGE, height=12)
    dup_lbl.pack(fill="x", padx=26, pady=(0, 2))

    _dup_timer = [None]          # debounce handle
    # Pre-build hash set for O(1) duplicate lookups
    _pw_hash_map: dict[str, str] = {}
    _own_id = entry.get("id") if is_edit else None
    for oe in app.data["entries"]:
        if oe.get("id") == _own_id:
            continue
        op = oe.get("password", "")
        if op:
            _pw_hash_map[password_hash(op)] = oe.get("title", "?")

    def _check_dup():
        """Duplicate check (runs after debounce delay)."""
        pw = pass_e.get()
        if pw:
            dupe_title = _pw_hash_map.get(password_hash(pw))
            if dupe_title:
                dup_lbl.configure(
                    text=t("⚠️ Same password used in '{title}'",
                           title=dupe_title))
                return
        dup_lbl.configure(text="")

    def upd_str(e=None):
        pw = pass_e.get()
        s, l, c = password_strength(pw)
        str_bar.set(s / 4)
        str_bar.configure(progress_color=c)
        str_lbl.configure(text=l, text_color=c)
        # Debounced duplicate check (300ms)
        if _dup_timer[0]:
            dlg.after_cancel(_dup_timer[0])
        _dup_timer[0] = dlg.after(300, _check_dup)

    pass_e.bind("<KeyRelease>", upd_str)
    if is_edit:
        upd_str()

    # COLOR picker
    g_color = ios_group(scroll, "Color", compact=True)
    color_row = ctk.CTkFrame(g_color, fg_color="transparent")
    color_row.pack(fill="x", padx=10, pady=4)
    _def_color = app.settings.get("default_card_color", "default")
    current_color = ctk.StringVar(
        value=entry.get("color", "default") if is_edit else _def_color)

    color_btns = {}
    for ckey, info in CARD_COLORS.items():
        btn_color = info["strip"] if info["strip"] else BG_TERT
        is_selected = current_color.get() == ckey
        b = ctk.CTkButton(
            color_row, text="✓" if is_selected else "",
            width=24, height=24, fg_color=btn_color,
            hover_color=btn_color, corner_radius=12,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_ON_ACCENT,
            command=lambda k=ckey: _select_color(k))
        b.pack(side=side_start(), padx=2)
        color_btns[ckey] = b
        tip(b, t("{label} card color", label=t(info["label"])))

    def _select_color(k):
        current_color.set(k)
        for ck, cb in color_btns.items():
            cb.configure(text="✓" if ck == k else "")

    # NOTES
    g3 = ios_group(scroll, "Notes", compact=True)
    notes_val = entry.get("notes", "") if is_edit else ""
    notes_tb = ios_field(g3, "Notes", idx=0, is_textbox=True,
                          height=32, value=notes_val)

    # ── ADVANCED ──
    # Everything below is per-entry machinery most entries never use:
    # auto-type matching for one, an SSH key for another. Left open,
    # it pushed the four fields nearly every entry *does* use into a
    # minority of the form. Collapsed, with the header naming what is
    # set inside — hidden is fine, silently in force is not.
    patterns_val = entry.get("match_patterns", "") if is_edit else ""
    if isinstance(patterns_val, (list, tuple)):
        patterns_val = "\n".join(patterns_val)
    seq_val = (entry.get("autotype_sequence", "") if is_edit else "")
    general_val = (bool(entry.get("general_account", False))
                   if is_edit else False)
    key_source_val = (entry.get("ssh_key_source", "none")
                      if is_edit else "none")
    key_path_val = entry.get("ssh_key_path", "") if is_edit else ""
    stored_key_val = entry.get("ssh_key", "") if is_edit else ""

    def advanced_summary():
        parts = []
        if patterns_val.strip() or seq_val.strip() or general_val:
            parts.append(t("auto-type"))
        if key_source_val != "none":
            parts.append(t("SSH key"))
        return "· " + ", ".join(parts) if parts else ""

    adv_open = bool(
        patterns_val.strip() or general_val or key_source_val != "none"
        # An entry already filed under a server category is one whose
        # key fields are worth seeing without hunting for them.
        or app._server_category(cat_val))
    advanced["nudged"] = adv_open
    g4 = collapsible_group(
        scroll, "Advanced", open_now=adv_open,
        summary=advanced_summary, compact=True)
    advanced["group"] = g4

    patterns_tb = ios_field(
        g4, "Window patterns", idx=0, is_textbox=True, height=44,
        value=patterns_val, ltr=True)
    tip(patterns_tb,
        t("One per line. A window whose title matches gets this "
          "entry: *.corp.local, intranet, 10.0.0.*"))

    seq_e = ios_field(g4, "Typing order", idx=1,
                      value=seq_val or AUTOTYPE_DEFAULT, ltr=True)
    seq_hint = ctk.CTkLabel(
        g4, text="", font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        anchor=anchor_start())
    seq_hint.pack(fill="x", padx=(58, 12), pady=(0, 2))

    def _show_sequence_plain(*_args):
        # "{USERNAME}{TAB}{PASSWORD}" says nothing until you have read
        # the syntax. The plain reading sits under it.
        seq_hint.configure(
            text=autotype_sequence.describe(seq_e.get().strip()
                                            or AUTOTYPE_DEFAULT))

    seq_e.bind("<KeyRelease>", _show_sequence_plain, add="+")
    _show_sequence_plain()

    general_row = ctk.CTkFrame(g4, fg_color="transparent")
    general_row.pack(fill="x", padx=12, pady=(2, 8))
    general_var = ctk.BooleanVar(value=general_val)
    # The label is a separate widget: CTkCheckBox has no `anchor`, so
    # its own text cannot follow the reading direction, and passing
    # one raises rather than being ignored.
    ctk.CTkCheckBox(
        general_row, text="", width=24, checkbox_width=20,
        checkbox_height=20, variable=general_var, fg_color=ACCENT,
        hover_color=ACCENT_HOVER, corner_radius=5,
        border_width=2).pack(side=side_start())
    ctk.CTkLabel(
        general_row,
        text=t("Offer this account for any window, on request"),
        font=ctk.CTkFont(size=11), text_color=TEXT_SEC,
        anchor=anchor_start()).pack(
        side=side_start(), fill="x", expand=True, padx=pad(6, 0))

    key_widgets = ssh_key_section(
        app, g4, key_source_val, key_path_val, stored_key_val,
        entry.get("title", "") if is_edit else "")

    # Bottom
    bottom = ctk.CTkFrame(dlg, fg_color="transparent")
    bottom.pack(fill="x", padx=14, pady=(0, 10))

    err = ctk.CTkLabel(bottom, text="", text_color=RED,
                        font=ctk.CTkFont(size=10), height=12)
    err.pack(pady=(0, 2))

    def save():
        # Not `t`: that is the translation function, and binding it
        # here made every validation message in this function a call
        # on a string. Leaving the title empty and pressing Save
        # raised `'str' object is not callable` instead of saying
        # "Title is required" — the two error paths that exist to
        # catch a mistake were themselves the crash.
        title_v = title_e.get().strip()
        p = pass_e.get().strip()
        if not title_v:
            err.configure(text=t("⚠️ Title is required"))
            return
        if not p:
            err.configure(text=t("⚠️ Password is required"))
            return
        u = user_e.get().strip()
        c = cat_cb.get().strip()
        n = notes_tb.get("1.0", "end").strip()
        col = current_color.get()
        url_v = url_e.get().strip()
        patterns = patterns_tb.get("1.0", "end").strip()
        sequence = seq_e.get().strip() or AUTOTYPE_DEFAULT
        key_source, key_path, stored_key, key_problem = \
            key_widgets["read"]()
        if key_problem:
            err.configure(text=t("⚠️ SSH key: {problem}",
                                 problem=key_problem))
            return
        # Refused here rather than at typing time: a sequence that
        # cannot be carried out is only discovered when someone is
        # standing in front of a login box waiting for it.
        problem = autotype_sequence.validate(sequence)
        if problem:
            err.configure(text=t("⚠️ Typing order: {problem}",
                                 problem=problem))
            return
        general = bool(general_var.get())
        now_iso = datetime.datetime.now().isoformat()

        if is_edit:
            entry.update(title=title_v, username=u, password=p,
                          url=url_v, category=c, notes=n,
                          color=col, modified_at=now_iso,
                          match_patterns=patterns,
                          autotype_sequence=sequence,
                          general_account=general,
                          ssh_key_source=key_source,
                          ssh_key_path=key_path,
                          ssh_key=stored_key)
        else:
            app.data["entries"].append({
                "id": str(uuid.uuid4()), "title": title_v,
                "username": u, "password": p, "url": url_v,
                "category": c, "notes": n, "color": col,
                "pinned": False, "created_at": now_iso,
                "modified_at": now_iso,
                "match_patterns": patterns,
                "autotype_sequence": sequence,
                "general_account": general,
                "ssh_key_source": key_source,
                "ssh_key_path": key_path,
                "ssh_key": stored_key,
            })
        app._save_guarded()
        dlg.destroy()
        app.refresh_categories()
        app.refresh_entries()


    save_btn = ctk.CTkButton(
        bottom,
        text=(t("💾  Save Changes") if is_edit
              else t("💾  Save")),
        height=36,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
        command=save)
    save_btn.pack(fill="x")
    tip(save_btn, t("Save this password entry"))
    dlg.bind("<Control-Return>", lambda _e: save())
    # Enter submits from any single-line field, the way the smaller
    # dialogs already behave. The Notes box keeps Enter for newlines.
    for field in (title_e, url_e, user_e, pass_e):
        field.bind("<Return>", lambda _e: save())
    # A CTkTextbox swallows Tab as an indent character, which trapped
    # keyboard focus in Notes with no way out.
    def _leave_notes(target):
        def handler(_event):
            target.focus_set()
            return "break"
        return handler

    notes_tb.bind("<Tab>", _leave_notes(save_btn))
    notes_tb.bind("<Shift-Tab>", _leave_notes(pass_e))
    title_e.focus()
