"""Export / Import data dialogs."""

from __future__ import annotations

import csv
import logging
import os
import threading
import tkinter as tk

import customtkinter as ctk
from tkinter import filedialog as tkfiledialog

from ...i18n import anchor_start, pad, side_end, side_start, t
from ...crypto import save_data
from ...export_import import (
    HAS_OPENPYXL, MAX_IMPORT_BYTES, MAX_IMPORT_ROWS,
    export_csv, export_excel, import_csv, import_excel, read_headers,
)
from ...import_profiles import (
    PROFILES, describe, detect, unmapped_headers,
)
from ...security import find_new_entries
from ...theme import (
    ACCENT, ACCENT_HOVER, BG_TERT, CARD_HOVER, GREEN, GREEN_HOVER,
    ORANGE, RED, TEXT_ON_GREEN, TEXT_PRI, TEXT_SEC, WARN_BG,
)
from ..widgets import dialog_header, tip

log = logging.getLogger("PasswordVault")

# Dropdown entry that leaves the format to the header-row heuristic.
AUTO_DETECT = t("Auto-detect")


def show_export(app) -> None:
    dlg = app._make_dialog("Export Data", 420, 280)

    dialog_header(dlg, "Export Data", icon="📤", pady=(16, 4))

    warn = ctk.CTkFrame(dlg, fg_color=WARN_BG, corner_radius=10)
    warn.pack(fill="x", padx=20, pady=(8, 12))
    ctk.CTkLabel(warn,
                  text=t("⚠️  The exported file will contain all your\n"
                       "passwords in PLAIN TEXT. Keep it secure!"),
                  font=ctk.CTkFont(family="Segoe UI", size=11),
                  text_color=ORANGE, justify="center").pack(
        padx=12, pady=8)

    total = len(app.data.get("entries", []))
    ctk.CTkLabel(dlg,
                  text=t("📊  {count} entries will be exported",
                         count=total),
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
            _fail(t("Could not write the file: {error}",
                    error=exc.strerror or exc))
            return
        dlg.destroy()

    def do_export_xlsx():
        status_lbl.configure(text="")
        if not HAS_OPENPYXL:
            _fail(t("Excel export needs the openpyxl package"))
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
            _fail(t("Could not write the file: {error}",
                    error=exc.strerror or exc))
            return
        dlg.destroy()

    ctk.CTkButton(
        bf, text=t("📄  Export CSV"), height=38,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
        corner_radius=10, command=do_export_csv).pack(
        side=side_start(), fill="x", expand=True, padx=pad(0, 4))
    tip_text = t("Export to Excel (.xlsx)")
    xlsx_btn = ctk.CTkButton(
        bf, text=t("📊  Export Excel"), height=38,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER,
        corner_radius=10, command=do_export_xlsx)
    xlsx_btn.pack(side=side_end(), fill="x", expand=True,
                  padx=pad(4, 0))
    if not HAS_OPENPYXL:
        xlsx_btn.configure(state="disabled", fg_color=BG_TERT)
        tip_text += t(" (install openpyxl)")
    tip(xlsx_btn, tip_text)

    ctk.CTkButton(
        dlg, text=t("Cancel"), height=32, width=100,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=8,
        command=dlg.destroy).pack(pady=(0, 12))


def show_import(app) -> None:
    dlg = app._make_dialog("Import Data", 420, 340)

    dialog_header(dlg, "Import Data", icon="📥", pady=(16, 8))

    ctk.CTkLabel(dlg,
                  text=t("Select a CSV or Excel file to import.\n"
                       "Exports from Chrome, Bitwarden, LastPass, "
                       "1Password,\nKeePass and Firefox are recognised too."),
                  font=ctk.CTkFont(size=11),
                  text_color=TEXT_SEC, justify="center").pack(
        pady=(0, 10))

    # Format row: the detected profile, with an override. Detection is
    # shown rather than assumed — a wrong guess would otherwise only
    # surface after the rows had already landed in the vault.
    fmt_row = ctk.CTkFrame(dlg, fg_color="transparent")
    fmt_row.pack(fill="x", padx=20, pady=(0, 6))
    ctk.CTkLabel(fmt_row, text=t("Format"),
                  font=ctk.CTkFont(family="Segoe UI", size=11),
                  text_color=TEXT_SEC,
                  anchor=anchor_start()).pack(side=side_start())
    fmt_var = ctk.StringVar(value=AUTO_DETECT)
    fmt_opt = ctk.CTkOptionMenu(
        fmt_row, values=[AUTO_DETECT] + [p.label for p in PROFILES],
        variable=fmt_var, width=190, height=28,
        font=ctk.CTkFont(size=11), fg_color=BG_TERT, button_color=ACCENT,
        button_hover_color=ACCENT_HOVER, text_color=TEXT_PRI,
        dropdown_fg_color=BG_TERT, dropdown_text_color=TEXT_PRI,
        command=lambda _choice: _reparse())
    fmt_opt.pack(side=side_end())
    tip(fmt_opt, t("Which application this file came from. Auto-detect reads "
                 "the header row; pick a format to override it."))

    fmt_lbl = ctk.CTkLabel(dlg, text="",
                            font=ctk.CTkFont(size=10),
                            text_color=TEXT_SEC)
    fmt_lbl.pack(pady=(0, 4))

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
    picked = {"path": "", "headers": []}

    def _alive() -> bool:
        try:
            return bool(dlg.winfo_exists())
        except tk.TclError:
            return False

    def _chosen_profile():
        """The profile to parse with: the override, or the detected one."""
        label = fmt_var.get()
        if label == AUTO_DETECT:
            return detect(picked["headers"]) if picked["headers"] else None
        return next((p for p in PROFILES if p.label == label), None)

    def _show_preview(entries):
        if not _alive():
            return
        busy["on"] = False
        browse_btn.configure(state="normal", text=t("📂  Browse File..."))
        import_data["entries"] = entries
        new = find_new_entries(app.data["entries"], entries)
        dup = len(entries) - len(new)
        info_lbl.configure(
            text=t("📊  Found {total} entries  |  New: {new}  |  "
                   "Duplicates: {dup}",
                   total=len(entries), new=len(new), dup=dup))

        notes = []
        if len(entries) >= MAX_IMPORT_ROWS:
            notes.append(t("Only the first {count} rows were read",
                           count=MAX_IMPORT_ROWS))
        profile = _chosen_profile()
        if profile is not None and picked["headers"]:
            if fmt_var.get() == AUTO_DETECT:
                fmt_lbl.configure(
                    text=t("Detected: {description}",
                           description=describe(
                               profile, picked["headers"])))
            else:
                fmt_lbl.configure(
                    text=t("Reading as {label}", label=profile.label))
            # Name the columns that will not survive, rather than letting
            # the user discover the loss after the fact.
            leftover = unmapped_headers(profile, picked["headers"])
            if leftover:
                notes.append(t(
                    "Columns not imported: {columns}",
                    columns=", ".join(leftover[:6])
                    + (" …" if len(leftover) > 6 else "")))
        if not entries:
            notes.append(
                t("No rows matched this format — try another one"))
        status_lbl.configure(text="⚠️ " + " · ".join(notes) if notes else "",
                             text_color=ORANGE if notes else GREEN)
        import_data["new_only"] = new
        import_data["all"] = entries

    def _show_error(message: str):
        if not _alive():
            return
        busy["on"] = False
        browse_btn.configure(state="normal", text=t("📂  Browse File..."))
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
            _show_error(t("File is too large to import"))
            return

        picked["path"] = path
        try:
            picked["headers"] = read_headers(path)
        except (OSError, ValueError, csv.Error) as ex:
            _show_error(str(ex))
            return
        _reparse()

    def _reparse():
        """Read the picked file under the currently selected profile.

        Switching the format dropdown re-reads rather than re-maps: the
        parse is cheap next to the file dialog, and re-reading keeps one
        code path for both the first read and every override.
        """
        path = picked["path"]
        if not path or busy["on"]:
            return
        profile = _chosen_profile()

        status_lbl.configure(text="")
        info_lbl.configure(text=t("⏳  Reading file…"))
        busy["on"] = True
        browse_btn.configure(state="disabled", text=t("⏳  Reading…"))

        def work():
            # Parsing a large CSV/workbook on the Tk thread freezes the
            # window; do it off-thread and marshal the result back.
            try:
                if path.lower().endswith(".xlsx"):
                    entries = import_excel(path, profile)
                else:
                    entries = import_csv(path, profile)
            except (OSError, ValueError, KeyError, csv.Error) as ex:
                app.root.after(0, lambda ex=ex: _show_error(str(ex)))
                return
            app.root.after(0, lambda: _show_preview(entries))

        threading.Thread(target=work, daemon=True).start()

    browse_btn = ctk.CTkButton(
        dlg, text=t("📂  Browse File..."), height=36, width=200,
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
                text=t("⚠️ No entries to import"),
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
                text=t("⚠️ Could not save the import — nothing was changed"),
                text_color=RED)
            return
        app.refresh_categories()
        app.refresh_entries()
        dlg.destroy()

    ctk.CTkButton(
        bf, text=t("Import (Skip Dups)"), height=36,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=TEXT_ON_GREEN,
        corner_radius=10,
        command=lambda: do_import(True)).pack(
        side=side_start(), fill="x", expand=True, padx=pad(0, 4))
    ctk.CTkButton(
        bf, text=t("Import All"), height=36,
        font=ctk.CTkFont(size=12, weight="bold"),
        fg_color=ACCENT, hover_color=ACCENT_HOVER,
        corner_radius=10,
        command=lambda: do_import(False)).pack(
        side=side_end(), fill="x", expand=True, padx=pad(4, 0))

    ctk.CTkButton(
        dlg, text=t("Cancel"), height=32, width=100,
        font=ctk.CTkFont(size=12), fg_color=BG_TERT,
        hover_color=CARD_HOVER, corner_radius=8,
        command=dlg.destroy).pack(pady=(0, 12))
