"""
CSV and Excel export / import helpers.
"""

from __future__ import annotations

import csv
import datetime
import uuid

try:
    import openpyxl
    import openpyxl.styles
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

EXPORT_COLS = ["Title", "Username", "Password", "URL", "Category",
               "Notes", "Color", "Created", "Modified"]

_FIELD_MAP = {"Title": "title", "Username": "username", "Password": "password",
              "URL": "url", "Category": "category", "Notes": "notes",
              "Color": "color", "Created": "created_at", "Modified": "modified_at"}


def _entry_to_row(e: dict) -> list[str]:
    return [e.get(f, "") for f in
            ["title", "username", "password", "url", "category",
             "notes", "color", "created_at", "modified_at"]]


def _row_to_entry(d: dict) -> dict:
    """Convert a dict with header-keyed values to an entry dict."""
    now_iso = datetime.datetime.now().isoformat()
    return {
        "id": str(uuid.uuid4()),
        "title": d.get("Title", d.get("title", "")),
        "username": d.get("Username", d.get("username", "")),
        "password": d.get("Password", d.get("password", "")),
        "url": d.get("URL", d.get("url", "")),
        "category": d.get("Category", d.get("category", "General")) or "General",
        "notes": d.get("Notes", d.get("notes", "")),
        "color": d.get("Color", d.get("color", "default")) or "default",
        "pinned": False,
        "created_at": d.get("Created", d.get("created_at", now_iso)) or now_iso,
        "modified_at": now_iso,
    }


def export_csv(entries: list[dict], filepath: str) -> None:
    """Export entries to a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_COLS)
        for e in entries:
            w.writerow(_entry_to_row(e))


def export_excel(entries: list[dict], filepath: str) -> bool:
    """Export entries to an Excel (.xlsx) file. Returns False if openpyxl missing."""
    if not HAS_OPENPYXL:
        return False
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Passwords"
    ws.append(EXPORT_COLS)
    for cell in ws[1]:
        cell.font = openpyxl.styles.Font(bold=True)
    for e in entries:
        ws.append(_entry_to_row(e))
    for col in ws.columns:
        ml = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(ml + 2, 40)
    wb.save(filepath)
    return True


def import_csv(filepath: str) -> list[dict]:
    """Import entries from a CSV file."""
    entries: list[dict] = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            e = _row_to_entry(row)
            if e["title"] or e["password"]:
                entries.append(e)
    return entries


def import_excel(filepath: str) -> list[dict]:
    """Import entries from an Excel (.xlsx) file."""
    if not HAS_OPENPYXL:
        return []
    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        wb.close()
        return []
    headers = [str(h).strip() if h else "" for h in rows[0]]
    entries: list[dict] = []
    for row in rows[1:]:
        d = dict(zip(headers, [str(v) if v else "" for v in row]))
        e = _row_to_entry(d)
        if e["title"] or e["password"]:
            entries.append(e)
    wb.close()
    return entries

