"""Password Generator dialog."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...security import generate_password, password_strength
from ...settings import save_settings
from ...theme import (
    ACCENT, ACCENT_HOVER, BG_SEC, BG_TERT, GREEN, GREEN_HOVER,
    TEXT_ON_GREEN, TEXT_PRI, TEXT_QUAT, TEXT_SEC,
)
from ..widgets import tip

# Idle time after the length slider settles before regenerating.
REGEN_DEBOUNCE_MS = 120


def show(app, target_entry) -> None:
    dlg = app._make_dialog("Password Generator", 380, 330)

    ctk.CTkLabel(
        dlg, text="🎲  Password Generator",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_PRI).pack(pady=(14, 8))

    frm = ctk.CTkFrame(dlg, fg_color="transparent")
    frm.pack(fill="both", expand=True, padx=18, pady=(0, 10))

    _gl = app.settings.get("gen_length", 16)
    gen_var = ctk.StringVar(value=generate_password(
        _gl,
        app.settings.get("gen_upper", True),
        app.settings.get("gen_lower", True),
        app.settings.get("gen_digits", True),
        app.settings.get("gen_symbols", True)))
    gen_entry = ctk.CTkEntry(
        frm, height=38,
        font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
        textvariable=gen_var, fg_color=BG_SEC, border_width=1,
        border_color=ACCENT, corner_radius=10, justify="center",
        text_color=TEXT_PRI)
    gen_entry.pack(fill="x", pady=(0, 5))
    tip(gen_entry, "Generated password — click Use This to apply it")

    sf = ctk.CTkFrame(frm, fg_color="transparent")
    sf.pack(fill="x", pady=(0, 8))
    sb = ctk.CTkProgressBar(sf, height=4, corner_radius=2,
                              fg_color=BG_TERT, progress_color=GREEN)
    sb.pack(side="left", fill="x", expand=True)
    sl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont(size=9),
                        text_color=GREEN)
    sl.pack(side="left", padx=(6, 0))

    lv = ctk.IntVar(value=_gl)
    uv = ctk.BooleanVar(value=app.settings.get("gen_upper", True))
    lov = ctk.BooleanVar(value=app.settings.get("gen_lower", True))
    dv = ctk.BooleanVar(value=app.settings.get("gen_digits", True))
    sv = ctk.BooleanVar(value=app.settings.get("gen_symbols", True))

    lf = ctk.CTkFrame(frm, fg_color="transparent")
    lf.pack(fill="x", pady=(0, 5))
    ctk.CTkLabel(lf, text="Length:",
                  font=ctk.CTkFont(size=11),
                  text_color=TEXT_SEC).pack(side="left")
    ll = ctk.CTkLabel(lf, text=str(_gl),
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=TEXT_PRI, width=28)
    ll.pack(side="right")

    def regen(*_):
        pw = generate_password(lv.get(), uv.get(), lov.get(),
                                dv.get(), sv.get())
        gen_var.set(pw)
        s, l, c = password_strength(pw)
        sb.set(s / 4)
        sb.configure(progress_color=c)
        sl.configure(text=l, text_color=c)

    _regen_timer: list = [None]

    def on_len(v):
        # The slider fires on every step of the drag; the label follows
        # immediately but regeneration waits for the drag to settle.
        lv.set(int(v))
        ll.configure(text=str(int(v)))
        if _regen_timer[0]:
            try:
                dlg.after_cancel(_regen_timer[0])
            except (tk.TclError, ValueError):
                pass
        _regen_timer[0] = dlg.after(REGEN_DEBOUNCE_MS, regen)

    slider = ctk.CTkSlider(
        lf, from_=6, to=40, number_of_steps=34, command=on_len,
        fg_color=BG_TERT, progress_color=ACCENT,
        button_color=ACCENT, button_hover_color=ACCENT_HOVER)
    slider.set(_gl)
    slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
    tip(slider, "Drag to change password length")

    cf = ctk.CTkFrame(frm, fg_color="transparent")
    cf.pack(fill="x", pady=(0, 8))
    for txt, var, desc in [
        ("ABC", uv, "Include uppercase letters"),
        ("abc", lov, "Include lowercase letters"),
        ("123", dv, "Include digits"),
        ("#$%", sv, "Include special characters"),
    ]:
        chk = ctk.CTkCheckBox(
            cf, text=txt, variable=var,
            font=ctk.CTkFont(size=11),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=regen)
        chk.pack(side="left", padx=(0, 10))
        tip(chk, desc)

    bf = ctk.CTkFrame(frm, fg_color="transparent")
    bf.pack(fill="x")
    regen_btn = ctk.CTkButton(
        bf, text="🔄  Regenerate", height=32,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=TEXT_QUAT, corner_radius=8, command=regen)
    regen_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
    tip(regen_btn, "Generate a new random password")

    def remember_options():
        """Persist the picked options so the next open starts here."""
        chosen = {"gen_length": lv.get(), "gen_upper": bool(uv.get()),
                  "gen_lower": bool(lov.get()), "gen_digits": bool(dv.get()),
                  "gen_symbols": bool(sv.get())}
        if all(app.settings.get(k) == v for k, v in chosen.items()):
            return
        app.settings.update(chosen)
        save_settings(app.settings)

    def use():
        target_entry.delete(0, "end")
        target_entry.insert(0, gen_var.get())
        remember_options()
        dlg.destroy()

    use_btn = ctk.CTkButton(
        bf, text="✅  Use This", height=32,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
        corner_radius=8, command=use)
    use_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
    tip(use_btn, "Apply this password to the entry")
    regen()
