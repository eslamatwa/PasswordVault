"""The Settings dialog.

Nine groups of preferences and one Save that applies them together.

Note the name: this is the *dialog*. The stored settings themselves live
in `password_vault/settings.py`, reached below as `...settings` -- an
explicit relative import, so the two never compete.
"""

from __future__ import annotations

import customtkinter as ctk

from ... import hotkeys
from ...i18n import (
    LANGUAGE_VALUES, anchor_start, label_for, ltr_justify, pad,
    set_language, side_end, side_start, t, value_for,
)
from ...settings import THEME_MODES, save_settings
from ...theme import (
    ACCENT, ACCENT_HOVER, BG_SEC, BG_TERT, CARD_COLORS, GREEN, INPUT_BG,
    RED, SEPARATOR, TEXT_ON_ACCENT, TEXT_PRI, TEXT_TERT,
)
from ..widgets import dialog_header, hotkey_field, ios_group, tip


def show(app):
    dlg = app._make_dialog("Settings", 480, 620)

    dialog_header(dlg, "Settings", icon="⚙️", size=17,
                  pady=(14, 6))

    scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                     scrollbar_button_color=BG_TERT)
    scroll.pack(fill="both", expand=True, padx=14, pady=(0, 6))

    s = dict(app.settings)

    def setting_row(group, icon, label, idx=0):
        if idx > 0:
            ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
                fill="x", padx=(46, 0))
        row = ctk.CTkFrame(group, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=5)
        lbl_w = ctk.CTkLabel(
            row, text=f"{icon}  {t(label)}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_PRI, anchor=anchor_start())
        lbl_w.pack(side=side_start(), fill="x", expand=True)
        return row, lbl_w

    # ── SECURITY ──
    g_sec = ios_group(scroll, "Security")

    r, lbl = setting_row(g_sec, "🔒", "Auto-Lock", idx=0)
    al_map = {t("{n} min", n=n): n for n in (1, 2, 5, 10, 15, 30)}
    al_map[t("Never")] = 0
    al_rev = {v: k for k, v in al_map.items()}
    al_var = ctk.StringVar(
        value=al_rev.get(s["auto_lock_minutes"], t("{n} min", n=5)))
    al_opt = ctk.CTkOptionMenu(
        r, values=list(al_map.keys()), variable=al_var,
        width=100, height=28, font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
    al_opt.pack(side=side_end())
    tip(lbl, t("Lock the vault after this period of inactivity. "
             "'Never' disables auto-lock."))

    r2, lbl2 = setting_row(g_sec, "🛡️", "Max Login Attempts", idx=1)
    att_map = {"3": 3, "5": 5, "10": 10, "15": 15}
    att_var = ctk.StringVar(value=str(s["max_login_attempts"]))
    att_opt = ctk.CTkOptionMenu(
        r2, values=list(att_map.keys()), variable=att_var,
        width=80, height=28, font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
    att_opt.pack(side=side_end())
    tip(lbl2, t("Maximum wrong password attempts before lockout."))

    r3, lbl3 = setting_row(g_sec, "⏱️", "Lockout Duration", idx=2)
    lo_map = {t("{n} sec", n=n): n for n in (15, 30, 60)}
    lo_map[t("{n} min", n=2)] = 120
    lo_map[t("{n} min", n=5)] = 300
    lo_rev = {v: k for k, v in lo_map.items()}
    lo_var = ctk.StringVar(
        value=lo_rev.get(s["lockout_seconds"], t("{n} sec", n=30)))
    lo_opt = ctk.CTkOptionMenu(
        r3, values=list(lo_map.keys()), variable=lo_var,
        width=100, height=28, font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
    lo_opt.pack(side=side_end())
    tip(lbl3, t("How long the vault stays locked after "
              "too many failed attempts."))

    r4, lbl4 = setting_row(g_sec, "📋", "Clear Clipboard", idx=3)
    cl_map = {t("Off"): 0}
    cl_map.update({t("{n} sec", n=n): n for n in (10, 15, 30, 60)})
    cl_rev = {v: k for k, v in cl_map.items()}
    cl_var = ctk.StringVar(
        value=cl_rev.get(s["clipboard_clear_seconds"], t("Off")))
    cl_opt = ctk.CTkOptionMenu(
        r4, values=list(cl_map.keys()), variable=cl_var,
        width=100, height=28, font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
    cl_opt.pack(side=side_end())
    tip(lbl4, t("Automatically clear copied passwords "
              "from clipboard after this time."))

    # ── REMOTE SESSIONS ──
    g_remote = ios_group(scroll, "Remote Sessions")
    r_cl, lbl_cl = setting_row(g_remote, "🖥️", "Extra SSH Client",
                               idx=0)
    client_var = ctk.StringVar(value=s.get("ssh_client_path", ""))
    client_e = ctk.CTkEntry(
        r_cl, textvariable=client_var, width=190, height=28,
        font=ctk.CTkFont(size=11), fg_color=INPUT_BG, border_width=0,
        corner_radius=6, text_color=TEXT_PRI, justify=ltr_justify(),
        placeholder_text=t("full path to an .exe"))
    client_e.pack(side=side_end())
    tip(lbl_cl,
        t("MobaXterm, PuTTY and Windows SSH are found automatically. "
          "Point at another client here — a portable copy, or one "
          "installed somewhere unusual."))

    r_hk, lbl_hk = setting_row(g_remote, "🔑", "Verify host keys",
                               idx=1)
    verify_hosts = ctk.BooleanVar(
        value=s.get("verify_host_keys", False))
    ctk.CTkSwitch(
        r_hk, text="", variable=verify_hosts, width=44,
        progress_color=ACCENT, button_color=TEXT_PRI).pack(
        side=side_end())
    tip(lbl_hk,
        t("Fetch the server's key before connecting and refuse if it "
          "has changed. Costs a moment per connection, and needs "
          "outbound port 22."))

    # ── AUTO-TYPE ──
    g_auto = ios_group(scroll, "Auto-Type")
    r_at, lbl_at = setting_row(g_auto, "⌨️", "Enable Auto-Type", idx=0)
    autotype_on = ctk.BooleanVar(
        value=s.get("autotype_enabled", False))
    ctk.CTkSwitch(
        r_at, text="", variable=autotype_on, width=44,
        progress_color=ACCENT, button_color=TEXT_PRI).pack(
        side=side_end())
    tip(lbl_at,
        t("Types the username and password into whatever window is "
          "in front. Off until you ask for it."))

    hotkey_vars = {}
    rows = (("autotype_hotkey_full", "Fill username + password", 1),
            ("autotype_hotkey_username", "Username only", 2),
            ("autotype_hotkey_password", "Password only", 3))
    for key, label, idx in rows:
        row, row_label = setting_row(g_auto, "⌨️", label, idx=idx)
        var = ctk.StringVar(value=s.get(key, ""))
        hotkey_vars[key] = var
        hotkey_field(row, var.get(),
                     lambda value, v=var: v.set(value)).pack(
            side=side_end())
        tip(row_label,
            t("Click, then press the combination you want."))

    ctk.CTkLabel(
        g_auto,
        text=t("A window running as administrator cannot be typed "
               "into — Windows blocks input from a normal program, "
               "and this app deliberately never asks for admin."),
        font=ctk.CTkFont(size=9), text_color=TEXT_TERT,
        wraplength=380, justify="left",
        anchor=anchor_start()).pack(fill="x", padx=14, pady=(2, 8))

    # ── PASSWORD GENERATOR ──
    g_gen = ios_group(scroll, "Password Generator Defaults")

    r5, lbl5 = setting_row(g_gen, "📏", "Default Length", idx=0)
    gl_var = ctk.IntVar(value=s.get("gen_length", 16))
    gl_lbl = ctk.CTkLabel(r5, text=str(gl_var.get()),
                            font=ctk.CTkFont(size=11, weight="bold"),
                            text_color=TEXT_PRI, width=28)
    gl_lbl.pack(side=side_end())

    def on_gl(v):
        gl_var.set(int(float(v)))
        gl_lbl.configure(text=str(int(float(v))))

    gl_slider = ctk.CTkSlider(
        r5, from_=6, to=40, number_of_steps=34, command=on_gl,
        width=140, fg_color=BG_TERT, progress_color=ACCENT,
        button_color=ACCENT, button_hover_color=ACCENT_HOVER)
    gl_slider.set(gl_var.get())
    gl_slider.pack(side=side_end(), padx=pad(0, 8))
    tip(lbl5, t("Default password length when opening the generator."))

    r6, lbl6 = setting_row(g_gen, "🔤", "Uppercase (ABC)", idx=1)
    gen_upper = ctk.CTkSwitch(r6, text="", width=46,
                                fg_color=BG_TERT, progress_color=GREEN,
                                button_color=TEXT_PRI)
    gen_upper.pack(side=side_end())
    if s.get("gen_upper", True):
        gen_upper.select()
    tip(lbl6, t("Include uppercase letters (A-Z)."))

    r7, lbl7 = setting_row(g_gen, "🔡", "Lowercase (abc)", idx=2)
    gen_lower = ctk.CTkSwitch(r7, text="", width=46,
                                fg_color=BG_TERT, progress_color=GREEN,
                                button_color=TEXT_PRI)
    gen_lower.pack(side=side_end())
    if s.get("gen_lower", True):
        gen_lower.select()
    tip(lbl7, t("Include lowercase letters (a-z)."))

    r8, lbl8 = setting_row(g_gen, "🔢", "Digits (0-9)", idx=3)
    gen_digits = ctk.CTkSwitch(r8, text="", width=46,
                                 fg_color=BG_TERT, progress_color=GREEN,
                                 button_color=TEXT_PRI)
    gen_digits.pack(side=side_end())
    if s.get("gen_digits", True):
        gen_digits.select()
    tip(lbl8, t("Include digits (0-9)."))

    r9, lbl9 = setting_row(g_gen, "🔣", "Symbols (#$%&)", idx=4)
    gen_symbols = ctk.CTkSwitch(r9, text="", width=46,
                                  fg_color=BG_TERT, progress_color=GREEN,
                                  button_color=TEXT_PRI)
    gen_symbols.pack(side=side_end())
    if s.get("gen_symbols", True):
        gen_symbols.select()
    tip(lbl9, t("Include special symbols (!@#$%&)."))

    # ── APPEARANCE ──
    g_app = ios_group(scroll, "Appearance")

    r_th, lbl_th = setting_row(g_app, "🌗", "Theme", idx=0)
    theme_labels = {t("System"): "System", t("Dark"): "Dark",
                    t("Light"): "Light"}
    assert set(theme_labels.values()) == set(THEME_MODES)
    theme_names = {mode: label
                   for label, mode in theme_labels.items()}
    th_var = ctk.StringVar(
        value=theme_names.get(s.get("theme", "Dark"), t("Dark")))
    th_opt = ctk.CTkOptionMenu(
        r_th, values=list(theme_labels), variable=th_var,
        width=100, height=28, font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI,
        command=lambda choice: app._apply_appearance(
            theme_labels.get(choice, "Dark")))
    th_opt.pack(side=side_end())
    tip(lbl_th, t("Light, dark, or follow the Windows setting. "
                "Applies immediately."))

    r_lang, lbl_lang = setting_row(g_app, "🌐", t("Language"), idx=1)
    lang_var = ctk.StringVar(
        value=label_for(s.get("language", "English")))
    lang_opt = ctk.CTkOptionMenu(
        r_lang, values=[label_for(v) for v in LANGUAGE_VALUES],
        variable=lang_var, width=100, height=28,
        font=ctk.CTkFont(size=11),
        fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_SEC, dropdown_text_color=TEXT_PRI)
    lang_opt.pack(side=side_end())
    tip(lbl_lang, t("The window is rebuilt when the language changes."))

    r10, lbl10 = setting_row(g_app, "🎨", t("Default Card Color"), idx=2)
    tip(lbl10, t("Default color for new password entries."))

    def_color_var = ctk.StringVar(
        value=s.get("default_card_color", "default"))
    color_btns = {}
    color_row = ctk.CTkFrame(g_app, fg_color="transparent")
    color_row.pack(fill="x", padx=12, pady=(0, 6))
    for ckey, info in CARD_COLORS.items():
        btn_color = info["strip"] if info["strip"] else BG_TERT
        is_sel = def_color_var.get() == ckey
        b = ctk.CTkButton(
            color_row, text="✓" if is_sel else "",
            width=28, height=28, fg_color=btn_color,
            hover_color=btn_color, corner_radius=14,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_ON_ACCENT,
            command=lambda k=ckey: _sel_def_color(k))
        b.pack(side=side_start(), padx=3)
        color_btns[ckey] = b
        tip(b, t("{label} — set as default card color",
                 label=t(info["label"])))

    def _sel_def_color(k):
        def_color_var.set(k)
        for ck, cb in color_btns.items():
            cb.configure(text="✓" if ck == k else "")

    # ── BEHAVIOR ──
    g_beh = ios_group(scroll, "Behavior")

    r11, lbl11 = setting_row(g_beh, "🚀", "Start Minimized", idx=0)
    start_min = ctk.CTkSwitch(r11, text="", width=46,
                                fg_color=BG_TERT, progress_color=GREEN,
                                button_color=TEXT_PRI)
    start_min.pack(side=side_end())
    if s.get("start_minimized", False):
        start_min.select()
    tip(lbl11, t("Start the app minimized to the floating widget."))

    # ── SAVE ──
    saved_theme = {"kept": False}

    def _revert_theme_preview(event):
        # The toplevel is in every child's bindtags, so <Destroy> also
        # arrives here for each child widget.
        if event.widget is not dlg or saved_theme["kept"]:
            return
        # The picker previews immediately; dismissing without saving must
        # not leave the app in a mode that is not stored.
        app._apply_appearance(app.settings.get("theme", "Dark"))

    dlg.bind("<Destroy>", _revert_theme_preview, add="+")

    def apply_settings():
        app.settings["auto_lock_minutes"] = al_map.get(
            al_var.get(), 5)
        app.settings["max_login_attempts"] = int(att_var.get())
        app.settings["lockout_seconds"] = lo_map.get(
            lo_var.get(), 30)
        app.settings["clipboard_clear_seconds"] = cl_map.get(
            cl_var.get(), 0)
        app.settings["ssh_client_path"] = client_var.get().strip()
        app.settings["verify_host_keys"] = bool(verify_hosts.get())
        app.settings["autotype_enabled"] = bool(autotype_on.get())
        for key, var in hotkey_vars.items():
            app.settings[key] = var.get().strip()
        clash = hotkeys.clashes({
            t("Fill username + password"):
                app.settings["autotype_hotkey_full"],
            t("Username only"):
                app.settings["autotype_hotkey_username"],
            t("Password only"):
                app.settings["autotype_hotkey_password"]})
        if clash:
            # Refused, not merely reported. Windows takes the first
            # registration and rejects the second without a word, so
            # saving anyway leaves one shortcut permanently dead
            # while the user believes both were accepted. The dialog
            # stays open, the same way the entry dialog refuses a
            # sequence it cannot carry out.
            first, second, combo = clash
            err.configure(text=t(
                "⚠️ {first} and {second} are both {combo}",
                first=first, second=second, combo=combo))
            return
        app.settings["gen_length"] = gl_var.get()
        app.settings["gen_upper"] = bool(gen_upper.get())
        app.settings["gen_lower"] = bool(gen_lower.get())
        app.settings["gen_digits"] = bool(gen_digits.get())
        app.settings["gen_symbols"] = bool(gen_symbols.get())
        app.settings["default_card_color"] = def_color_var.get()
        app.settings["start_minimized"] = bool(start_min.get())
        app.settings["theme"] = theme_labels.get(
            th_var.get(), "Dark")
        new_language = value_for(lang_var.get())
        language_changed = (
            new_language != app.settings.get("language", "English"))
        app.settings["language"] = new_language
        saved_theme["kept"] = True
        save_settings(app.settings)
        app._reset_idle(force=True)
        dlg.destroy()
        # Shortcuts are registered with Windows, so a change to them
        # means unregistering and asking again — settings alone do
        # nothing until that happens.
        app.restart_autotype()
        if language_changed:
            # Tk fixes anchor, justify, pack side and padding when a
            # widget is created and offers no way to re-flow them, so
            # the direction can only change by building again.
            set_language(new_language)
            app._rebuild_ui()

    bottom = ctk.CTkFrame(dlg, fg_color="transparent")
    bottom.pack(fill="x", padx=14, pady=(0, 12))
    err = ctk.CTkLabel(bottom, text="", text_color=RED,
                        font=ctk.CTkFont(size=10), height=14,
                        wraplength=380)
    err.pack(fill="x", pady=(0, 4))
    save_btn = ctk.CTkButton(
        bottom, text=t("💾  Save Settings"), height=40,
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
        command=apply_settings)
    save_btn.pack(fill="x")
    tip(save_btn, t("Save all settings and close"))
