"""Export / Import data dialogs."""

from __future__ import annotations

import csv

import customtkinter as ctk
from tkinter import filedialog as tkfiledialog

from ...crypto import save_data
from ...export_import import (
    HAS_OPENPYXL, export_csv, export_excel, import_csv, import_excel,
)
from ...theme import (
    ACCENT, ACCENT_HOVER, BG, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    ORANGE, RED, TEXT_PRI, TEXT_SEC,
)
from ..widgets import tip


def show_export(app) -> None:
    dlg = app._make_dialog("Export Data", 420, 280)

    ctk.CTkLabel(dlg, text="📤  Export Data",
                  font=ctk.CTkFont(family="Segoe UI", size=16,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(16, 4))

    warn = ctk.CTkFrame(dlg, fg_color="#3a2a20", corner_radius=10)
    warn.pack(fill="x", padx=20, pady=(8, 12))
    ctk.CTkLabel(warn,
                  text="⚠️  The exported file will contain all your\n"
                       "passwords in PLAIN TEXT. Keep it secure!",
                  font=ctk.CTkFont(family="Segoe UI", size=11),
                  text_color=ORANGE, justify="center").pack(
        padx=12, pady=8)

    total = len(app.data.get("entries", []))
    ctk.CTkLabel(dlg,
                  text=f"📊  {total} entries will be exported",
                  font=ctk.CTkFont(size=12),
                  text_color=TEXT_SEC).pack(pady=(0, 12))

    bf = ctk.CTkFrame(dlg, fg_color="transparent")
    bf.pack(fill="x", padx=20, pady=(0, 8))

    def do_export_csv():
        path = tkfiledialog.asksaveasfilename(
            parent=dlg, defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="passwords_export.csv")
        if path:
            export_csv(app.data["entries"], path)
            dlg.destroy()

    def do_export_xlsx():
        if not HAS_OPENPYXL:
            ctk.CTkLabel(dlg, text="⚠️ openpyxl not installed",
                          text_color=RED,
                          font=ctk.CTkFont(size=11)).pack()
            return
        path = tkfiledialog.asksaveasfilename(
            parent=dlg, defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="passwords_export.xlsx")
        if path:
            export_excel(app.data["entries"], path)
            dlg.destroy()

    ctk.CTkButton(
        bf, text="📄  Export CSV", height=38,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
        corner_radius=10, command=do_export_csv).pack(
        side="left", fill="x", expand=True, padx=(0, 4))
    tip_text = "Export to Excel (.xlsx)"
    xlsx_btn = ctk.CTkButton(
        bf, text="📊  Export Excel", height=38,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER,
        corner_radius=10, command=do_export_xlsx)
    xlsx_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
    if not HAS_OPENPYXL:
        xlsx_btn.configure(state="disabled", fg_color=BG_TERT)
        tip_text += " (install openpyxl)"
    tip(xlsx_btn, tip_text)

    ctk.CTkButton(
        dlg, text="Cancel", height=32, width=100,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=8,
        command=dlg.destroy).pack(pady=(0, 12))


def show_import(app) -> None:
    dlg = app._make_dialog("Import Data", 420, 340)

    ctk.CTkLabel(dlg, text="📥  Import Data",
                  font=ctk.CTkFont(family="Segoe UI", size=16,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(16, 8))

    ctk.CTkLabel(dlg,
                  text="Select a CSV or Excel file to import.\n"
                       "Columns: Title, Username, Password, "
                       "URL, Category, Notes",
                  font=ctk.CTkFont(size=11),
                  text_color=TEXT_SEC, justify="center").pack(
        pady=(0, 10))

    info_lbl = ctk.CTkLabel(dlg, text="",
                              font=ctk.CTkFont(size=12),
                              text_color=TEXT_PRI)
    info_lbl.pack(pady=(0, 8))

    status_lbl = ctk.CTkLabel(dlg, text="",
                                font=ctk.CTkFont(size=11),
                                text_color=GREEN)
    status_lbl.pack(pady=(0, 8))

    import_data = {"entries": []}

    def browse():
        ftypes = [("CSV files", "*.csv")]
        if HAS_OPENPYXL:
            ftypes.insert(0, ("Excel files", "*.xlsx"))
        ftypes.append(("All files", "*.*"))
        path = tkfiledialog.askopenfilename(
            parent=dlg, filetypes=ftypes)
        if not path:
            return
        try:
            if path.endswith(".xlsx"):
                entries = import_excel(path)
            else:
                entries = import_csv(path)
            import_data["entries"] = entries
            existing_titles = {
                (e.get("title", ""), e.get("username", ""))
                for e in app.data["entries"]}
            new = [e for e in entries
                   if (e["title"], e["username"])
                   not in existing_titles]
            dup = len(entries) - len(new)
            info_lbl.configure(
                text=f"📊  Found {len(entries)} entries  |  "
                     f"New: {len(new)}  |  Duplicates: {dup}")
            import_data["new_only"] = new
            import_data["all"] = entries
        except (OSError, ValueError, KeyError, csv.Error) as ex:
            info_lbl.configure(text=f"⚠️ Error: {ex}")

    ctk.CTkButton(
        dlg, text="📂  Browse File...", height=36, width=200,
        font=ctk.CTkFont(size=13), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=browse).pack(pady=(0, 10))

    bf = ctk.CTkFrame(dlg, fg_color="transparent")
    bf.pack(fill="x", padx=20, pady=(0, 8))

    def do_import(skip_dup):
        entries = (import_data.get("new_only", [])
                   if skip_dup
                   else import_data.get("all", []))
        if not entries:
            status_lbl.configure(
                text="⚠️ No entries to import",
                text_color=ORANGE)
            return
        existing_cats = set(app.data.get("categories", []))
        for e in entries:
            cat = e.get("category", "General")
            if cat and cat not in existing_cats:
                app.data["categories"].append(cat)
                existing_cats.add(cat)
        app.data["entries"].extend(entries)
        save_data(app.data, app.key)
        app.refresh_categories()
        app.refresh_entries()
        dlg.destroy()

    ctk.CTkButton(
        bf, text="Import (Skip Dups)", height=36,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG,
        corner_radius=10,
        command=lambda: do_import(True)).pack(
        side="left", fill="x", expand=True, padx=(0, 4))
    ctk.CTkButton(
        bf, text="Import All", height=36,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER,
        corner_radius=10,
        command=lambda: do_import(False)).pack(
        side="right", fill="x", expand=True, padx=(4, 0))

    ctk.CTkButton(
        dlg, text="Cancel", height=32, width=100,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=8,
        command=dlg.destroy).pack(pady=(0, 12))
