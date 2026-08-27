"""Measure how long the entry list takes to render.

    python tools/benchmark_ui.py

Rendering the list is the slowest thing the app does and the thing a user
waits on most often — it runs on startup, on every settled search
keystroke, on a category switch, and after any add, edit, delete or pin.
This exists so that work on it can be measured against a baseline rather
than guessed at, and so the numbers in MVP.md can be reproduced.

It prints three things:

1. **A control.** Plain Tk widgets on the same display. If those are slow
   too, the machine or the session is the bottleneck and nothing below
   means anything.
2. **Per-widget cost**, plain Tk against CustomTkinter. The ratio between
   them is the whole story: a CTk widget draws itself onto its own canvas,
   which is what makes a row of them expensive.
3. **The real list**, at vault sizes a person actually has.

Absolute numbers depend on the machine. The ratios do not.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import tkinter as tk

# Import the app against a throwaway APPDATA so a real vault is never
# touched by a benchmark run.
os.environ.setdefault("PV_BENCHMARK", "1")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="pv-benchmark-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402
import main as app_module  # noqa: E402


def _entries(n):
    return [{"id": str(i), "title": f"Service {i} account",
             "username": f"user{i}@example.com",
             "password": f"Str0ng!Passw0rd{i}",
             "url": f"https://service{i}.example.com/login",
             "category": "General", "notes": "",
             "color": ["default", "blue", "green"][i % 3],
             "pinned": i % 20 == 0,
             "created_at": "2024-01-01T00:00:00",
             "modified_at": "2025-06-01T00:00:00"}
            for i in range(n)]


def _count(widget):
    return 1 + sum(_count(c) for c in widget.winfo_children())


def control():
    """Plain Tk on this display, so app numbers can be read in context."""
    root = tk.Tk()
    root.geometry("900x700")
    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True)
    root.update()

    t0 = time.perf_counter()
    for i in range(1000):
        tk.Label(frame, text=f"row {i}").pack()
    build = time.perf_counter() - t0
    t0 = time.perf_counter()
    root.update()
    paint = time.perf_counter() - t0
    per = (build + paint) * 1000 / 1000
    root.destroy()

    print("=== control: is this display healthy? ===")
    print(f"   1000 plain tk.Labels        "
          f"{(build + paint) * 1000:8.0f} ms   {per:5.2f} ms/widget")
    if per > 1.0:
        print("   ! plain Tk is slow here; treat everything below as "
              "inflated by the same factor")
    return per


def widget_costs(app):
    """Priced inside the running app.

    A second CTk root would work, but tearing it down while CustomTkinter
    still has scheduled `after` callbacks prints a wall of Tcl errors that
    obscures the numbers.
    """
    host = ctk.CTkFrame(app.root)

    def cost(make, n=40):
        t0 = time.perf_counter()
        for _ in range(n):
            make()
        return (time.perf_counter() - t0) * 1000 / n

    rows = [("tk.Frame", cost(lambda: tk.Frame(host))),
            ("tk.Label", cost(lambda: tk.Label(host, text="x"))),
            ("CTkFrame", cost(lambda: ctk.CTkFrame(host))),
            ("CTkLabel", cost(lambda: ctk.CTkLabel(host, text="x"))),
            ("CTkButton", cost(lambda: ctk.CTkButton(host, text="x")))]
    host.destroy()

    print("\n=== cost of creating one widget ===")
    baseline = rows[1][1] or 1e-9
    for name, ms in rows:
        print(f"   {name:<12} {ms:7.2f} ms   {ms / baseline:5.1f}x a "
              f"tk.Label")
    return dict(rows)


def build_app():
    app = app_module.PasswordVault()
    app.key = b"0" * 44
    app._save_guarded = lambda: True
    app.data = {"categories": ["General"], "trash": [],
                "entries": _entries(1)}
    app.build_ui()
    app.root.update()
    return app


def list_render(app):
    # One card, to price a row.
    panel = app.entries_panel
    for w in panel.winfo_children():
        w.destroy()
    app.root.update()
    t0 = time.perf_counter()
    app._card(_entries(1)[0])
    app.root.update()
    one = (time.perf_counter() - t0) * 1000
    widgets = _count(panel.winfo_children()[-1])
    print("\n=== one entry card ===")
    print(f"   widgets per card            {widgets:8d}")
    print(f"   build + paint               {one:8.0f} ms")

    print(f"\n=== the list, at real vault sizes "
          f"(page size {app_module.ENTRIES_PAGE_SIZE}) ===")
    print(f"   {'entries':>8}  {'shown':>6}  {'repaint':>10}   feel")
    results = {}
    for n in (5, 10, 20, 40, 60, 100):
        app.data["entries"] = _entries(n)
        app._visible_limit = app_module.ENTRIES_PAGE_SIZE
        app.refresh_entries()
        app.root.update()                      # warm

        t0 = time.perf_counter()
        app.refresh_entries()
        app.root.update()
        elapsed = (time.perf_counter() - t0) * 1000
        results[n] = elapsed
        shown = min(n, app_module.ENTRIES_PAGE_SIZE)
        feel = ("instant" if elapsed < 100 else
                "fine" if elapsed < 300 else
                "laggy" if elapsed < 1000 else "too slow")
        print(f"   {n:>8}  {shown:>6}  {elapsed:>8.0f} ms   {feel}")

    return results


def main():
    per_plain = control()
    app = build_app()
    costs = widget_costs(app)
    results = list_render(app)
    app.root.destroy()

    print("\n=== summary ===")
    ratio = costs["CTkButton"] / (costs["tk.Label"] or 1e-9)
    print(f"   a CTkButton costs {ratio:.0f}x a plain tk.Label")
    if 20 in results:
        print(f"   a 20-entry vault repaints in {results[20]:.0f} ms")
    print(f"   plain-Tk baseline on this display: "
          f"{per_plain:.2f} ms/widget")
    print("\n   See MVP.md, 'Rendering the entry list', for what to do "
          "about it.")


if __name__ == "__main__":
    main()
