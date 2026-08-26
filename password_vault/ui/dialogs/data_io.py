"""Export / Import data dialogs."""

from __future__ import annotations

import csv
import logging
import os
import threading
import tkinter as tk

import customtkinter as ctk
from tkinter import filedialog as tkfiledialog

from ...crypto import save_data
from ...export_import import (
    HAS_OPENPYXL, MAX_IMPORT_BYTES, MAX_IMPORT_ROWS,
    export_csv, export_excel, import_csv, import_excel,
)
from ...security import find_new_entries
from ...theme import (
    ACCENT, ACCENT_HOVER, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    ORANGE, RED, TEXT_ON_GREEN, TEXT_PRI, TEXT_SEC, WARN_BG,
)
from ..widgets import tip

log = logging.getLogger("PasswordVault")


def show_export(app) -> None:
    dlg = app._make_dialog("Export Data", 420, 280)

    ctk.CTkLabel(dlg, text="📤  Export Data",
                  font=ctk.CTkFont(family="Segoe UI", size=16,
                                    weight="bold"),
                  text_color=TEXT_PRI).pack(pady=(16, 4))

    warn = ctk.CTkFrame(dlg, fg_color=WARN_BG, corner_radius=10)
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

    # One reused status line: every failed attempt used to pack a fresh
    # label, stacking messages down the dialog.
    status_lbl = ctk.CTkLabel(dlg, text="", font=ctk.CTkFont(size=11),
                              text_color=RED, wraplength=360,
                              justify="center")
    status_lbl.pack(fill="x", padx=20)

    bf = ctk.CTkFrame(dlg, fg_color="transparent")
    bf.pack(fill="x", padx=20, pady=(0, 8))

    def _fail(message: str):
        log.error("Export failed: %s", message)
        status_lbl.configure(text=f"⚠️ {message}", text_color=RED)

    def do_export_csv():
        status_lbl.configure(text="")
        path = tkfiledialog.asksaveasfilename(
            parent=dlg, defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="passwords_export.csv")
        if not path:
            return
        try:
            export_csv(app.data["entries"], path)
        except OSError as exc:
            _fail(f"Could not write the file: {exc.strerror or exc}")
            return
        dlg.destroy()

    def do_export_xlsx():
        status_lbl.configure(text="")
        if not HAS_OPENPYXL:
            _fail("Excel export needs the openpyxl package")
            return
        path = tkfiledialog.asksaveasfilename(
            parent=dlg, defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="passwords_export.xlsx")
        if not path:
            return
        try:
            export_excel(app.data["entries"], path)
        except OSError as exc:
            _fail(f"Could not write the file: {exc.strerror or exc}")
            return
        dlg.destroy()

    ctk.CTkButton(
        bf, text="📄  Export CSV", height=38,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
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
    busy = {"on": False}

    def _alive() -> bool:
        try:
            return bool(dlg.winfo_exists())
        except tk.TclError:
            return False

    def _show_preview(entries):
        if not _alive():
            return
        busy["on"] = False
        browse_btn.configure(state="normal", text="📂  Browse File...")
        import_data["entries"] = entries
        new = find_new_entries(app.data["entries"], entries)
        dup = len(entries) - len(new)
        info_lbl.configure(
            text=f"📊  Found {len(entries)} entries  |  "
                 f"New: {len(new)}  |  Duplicates: {dup}")
        if len(entries) >= MAX_IMPORT_ROWS:
            status_lbl.configure(
                text=f"⚠️ Only the first {MAX_IMPORT_ROWS} rows were read",
                text_color=ORANGE)
        import_data["new_only"] = new
        import_data["all"] = entries

    def _show_error(message: str):
        if not _alive():
            return
        busy["on"] = False
        browse_btn.configure(state="normal", text="📂  Browse File...")
        info_lbl.configure(text=f"⚠️ {message}")

    def browse():
        if busy["on"]:
            return
        ftypes = [("CSV files", "*.csv")]
        if HAS_OPENPYXL:
            ftypes.insert(0, ("Excel files", "*.xlsx"))
        ftypes.append(("All files", "*.*"))
        path = tkfiledialog.askopenfilename(
            parent=dlg, filetypes=ftypes)
        if not path:
            return
        try:
            size = os.path.getsize(path)
        except OSError as ex:
            _show_error(str(ex))
            return
        if size > MAX_IMPORT_BYTES:
            _show_error("File is too large to import")
            return

        status_lbl.configure(text="")
        info_lbl.configure(text="⏳  Reading file…")
        busy["on"] = True
        browse_btn.configure(state="disabled", text="⏳  Reading…")

        def work():
            # Parsing a large CSV/workbook on the Tk thread freezes the
            # window; do it off-thread and marshal the result back.
            try:
                if path.lower().endswith(".xlsx"):
                    entries = import_excel(path)
                else:
                    entries = import_csv(path)
            except (OSError, ValueError, KeyError, csv.Error) as ex:
                app.root.after(0, lambda ex=ex: _show_error(str(ex)))
                return
            app.root.after(0, lambda: _show_preview(entries))

        threading.Thread(target=work, daemon=True).start()

    browse_btn = ctk.CTkButton(
        dlg, text="📂  Browse File...", height=36, width=200,
        font=ctk.CTkFont(size=13), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=10,
        command=browse)
    browse_btn.pack(pady=(0, 10))

    bf = ctk.CTkFrame(dlg, fg_color="transparent")
    bf.pack(fill="x", padx=20, pady=(0, 8))

    def do_import(skip_dup):
        if busy["on"]:
            return
        entries = (import_data.get("new_only", [])
                   if skip_dup
                   else import_data.get("all", []))
        if not entries:
            status_lbl.configure(
                text="⚠️ No entries to import",
                text_color=ORANGE)
            return
        existing_cats = set(app.data.get("categories", []))
        added_cats = []
        for e in entries:
            cat = e.get("category", "General")
            if cat and cat not in existing_cats:
                app.data["categories"].append(cat)
                existing_cats.add(cat)
                added_cats.append(cat)
        app.data["entries"].extend(entries)
        try:
            save_data(app.data, app.key)
        except (OSError, ValueError) as ex:
            # Undo the in-memory import: showing rows that never reached
            # disk would let the user believe an import succeeded and then
            # lose everything at the next lock.
            del app.data["entries"][-len(entries):]
            for cat in added_cats:
                app.data["categories"].remove(cat)
            log.error("Import could not be saved: %s", ex, exc_info=True)
            status_lbl.configure(
                text="⚠️ Could not save the import — nothing was changed",
                text_color=RED)
            return
        app.refresh_categories()
        app.refresh_entries()
        dlg.destroy()

    ctk.CTkButton(
        bf, text="Import (Skip Dups)", height=36,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
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
