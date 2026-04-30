"""About dialog — version + author + features list."""

from __future__ import annotations

import customtkinter as ctk

from ... import APP_VERSION, APP_AUTHOR
from ...theme import (
    ACCENT, BG_TERT, CARD_HOVER, SEPARATOR,
    TEXT_PRI, TEXT_SEC,
)
from ..widgets import ios_group


def show(app) -> None:
    dlg = app._make_dialog("About Password Vault", 380, 440)

    circle = ctk.CTkFrame(dlg, width=80, height=80,
                            corner_radius=40, fg_color=ACCENT)
    circle.pack(pady=(24, 10))
    circle.pack_propagate(False)
    ctk.CTkLabel(circle, text="🔐", font=ctk.CTkFont(size=36),
                  fg_color="transparent").place(
        relx=0.5, rely=0.5, anchor="center")

    ctk.CTkLabel(dlg, text="Password Vault",
                  font=ctk.CTkFont(family="Segoe UI", size=22,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(0, 2))

    ver_frame = ctk.CTkFrame(dlg, fg_color=ACCENT, corner_radius=12)
    ver_frame.pack(pady=(0, 14))
    ctk.CTkLabel(ver_frame, text=f"  v{APP_VERSION}  ",
                  font=ctk.CTkFont(family="Segoe UI", size=11,
                                    weight="bold"),
                  text_color="white").pack(padx=8, pady=2)

    g = ios_group(dlg, "Information")

    def info_row(grp, icon, label, value, idx=0):
        if idx > 0:
            ctk.CTkFrame(grp, height=1, fg_color=SEPARATOR).pack(
                fill="x", padx=(46, 0))
        row = ctk.CTkFrame(grp, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row, text=f"{icon}  {label}",
                      font=ctk.CTkFont(family="Segoe UI", size=12),
                      text_color=TEXT_SEC, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=value,
                      font=ctk.CTkFont(family="Segoe UI", size=12,
                                        weight="bold"),
                      text_color=TEXT_PRI, anchor="e").pack(side="right")

    info_row(g, "📦", "Version", f"v{APP_VERSION}", idx=0)
    info_row(g, "👨‍💻", "Developer", APP_AUTHOR, idx=1)
    info_row(g, "🛡️", "Encryption", "AES-256 (Fernet)", idx=2)
    info_row(g, "🔑", "Key Derivation", "PBKDF2-SHA256", idx=3)
    info_row(g, "📂", "Data Location", "%APPDATA%", idx=4)

    g2 = ios_group(dlg, "Features")
    features = [
        "🔐  AES-256 encrypted local vault",
        "🎲  Secure password generator",
        "🔒  Auto-lock & brute-force protection",
        "📋  Quick-copy with auto-clear clipboard",
        "🎨  Custom card colors & categories",
        "📌  Favorites, Pin & Mini Vault",
        "🌐  URL field with browser open",
        "📤  Export / Import (CSV & Excel)",
        "🗑️  Recycle Bin for deleted entries",
        "🛡️  Security Dashboard & Breach Check",
        "⌨️  Keyboard shortcuts",
    ]
    for i, feat in enumerate(features):
        if i > 0:
            ctk.CTkFrame(g2, height=1, fg_color=SEPARATOR).pack(
                fill="x", padx=(16, 0))
        ctk.CTkLabel(g2, text=feat,
                      font=ctk.CTkFont(family="Segoe UI", size=11),
                      text_color=TEXT_PRI, anchor="w").pack(
            fill="x", padx=12, pady=3)

    ctk.CTkButton(
        dlg, text="Close", height=36, width=140,
        font=ctk.CTkFont(family="Segoe UI", size=13),
        fg_color=BG_TERT, hover_color=CARD_HOVER, corner_radius=10,
        command=dlg.destroy).pack(pady=(14, 16))
