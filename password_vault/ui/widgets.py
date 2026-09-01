"""
Reusable UI widgets: Tooltip, iOS-style form helpers, search bar.
"""

from __future__ import annotations

import functools
import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk

from ..i18n import (
    anchor_start, justify_start, ltr_justify, pad, side_end, side_start, t,
)
from ..theme import (
    BG_GROUP, BG_SEC, BG_TERT, CARD_HOVER, SEPARATOR, ACCENT, ACCENT_HOVER,
    INPUT_BG, TEXT_PRI, TEXT_SEC, TEXT_TERT, TEXT_QUAT,
    RED, TT_BG, TT_FG, cat_emoji, menu_style, resolve,
)


# ─── Shared Fonts ────────────────────────────────────────────
@functools.lru_cache(maxsize=None)
def ui_font(size: int = 12, weight: str = "normal",
            family: str | None = "Segoe UI") -> ctk.CTkFont:
    """Return a cached CTkFont for (size, weight, family).

    Every CTkFont instance registers itself with CustomTkinter's font
    manager, so creating one per widget inside a list-rendering loop costs
    thousands of objects for a large vault. Fonts are immutable here, so a
    single instance is safely shared by every widget that needs it.
    """
    if family:
        return ctk.CTkFont(family=family, size=size, weight=weight)
    return ctk.CTkFont(size=size, weight=weight)


# `modal_child` used to live here: a second, parallel way to take the grab,
# used only by the Recycle Bin's nested confirmations. Those went through
# `app._confirm` instead, which routes every dialog through the one
# `_grab_stack`, so the divergence is gone rather than documented.


_SEARCH_FIELDS = ("title", "username", "url", "category", "notes")


def filter_entries(entries: list[dict], category: str,
                   query: str) -> list[dict]:
    """Filter *entries* by category and free-text *query*.

    Shared by the main window and the Mini Vault so the same query cannot
    return different results in the two places.
    """
    if category and category != "All":
        entries = [e for e in entries if e.get("category") == category]
    query = (query or "").strip().lower()
    if not query:
        return entries
    return [e for e in entries
            if any(query in str(e.get(f, "")).lower()
                   for f in _SEARCH_FIELDS)]


def elide(text: str, limit: int) -> str:
    """Shorten *text* to *limit* characters with a trailing ellipsis.

    Card headers are single-line rows: an over-long title used to push the
    category badge and the action buttons out of the card.
    """
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "…"


# ─── Tooltip System ──────────────────────────────────────────
class Tooltip:
    _active: Tooltip | None = None

    def __init__(self, widget, text: str, delay: int = 400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except (tk.TclError, ValueError):
                pass
            self._after_id = None

    def _show(self):
        if Tooltip._active and Tooltip._active is not self:
            Tooltip._active._hide()
        if self._tip_window:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        bg, fg = resolve(TT_BG), resolve(TT_FG)
        tw.configure(bg=bg)
        frame = tk.Frame(tw, bg=bg, padx=10, pady=5)
        frame.pack()
        tk.Label(frame, text=self.text, bg=bg, fg=fg,
                 font=("Segoe UI", 10), wraplength=220,
                 justify=justify_start()).pack()
        tw.update_idletasks()
        tw_w = tw.winfo_reqwidth()
        x = x - tw_w // 2
        screen_w = self.widget.winfo_screenwidth()
        if x + tw_w > screen_w - 8:
            x = screen_w - tw_w - 8
        if x < 8:
            x = 8
        tw.wm_geometry(f"+{x}+{y}")
        Tooltip._active = self

    def _hide(self):
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None
        if Tooltip._active is self:
            Tooltip._active = None


def tip(widget, text: str) -> Tooltip:
    """Attach a tooltip to *widget*."""
    return Tooltip(widget, text)


def hotkey_field(parent, value, on_change, width=150, height=28):
    """A box you press a shortcut into, rather than spell out.

    Reads `event.keycode`, never `event.keysym`. On Windows the keycode
    is the virtual key -- the same number RegisterHotKey wants -- and it
    does not move with the keyboard layout. The keysym does: with Arabic
    active, Ctrl+Alt+V arrives with a keysym of '??', which is the trap
    this project already hit once with its Ctrl shortcuts.

    Escape puts back what was there. Delete clears it, which is how a
    shortcut is turned off.
    """
    from ..hotkeys import HotkeyError, from_event, is_modifier_key

    state = {"value": value or "", "armed": False}
    box = ctk.CTkEntry(parent, width=width, height=height,
                       font=ctk.CTkFont(size=11), fg_color=INPUT_BG,
                       border_width=0, corner_radius=6,
                       text_color=TEXT_PRI, justify="center")
    box.insert(0, state["value"] or t("not set"))

    def render(text, colour=TEXT_PRI):
        box.configure(state="normal")
        box.delete(0, "end")
        box.insert(0, text)
        box.configure(state="readonly", text_color=resolve(colour))

    render(state["value"] or t("not set"))

    def arm(_event=None):
        state["armed"] = True
        render(t("press the keys…"), ACCENT)

    def disarm(_event=None):
        state["armed"] = False
        render(state["value"] or t("not set"))

    def key(event):
        if not state["armed"]:
            return None
        if event.keysym == "Escape":
            disarm()
            return "break"
        if event.keysym in ("Delete", "BackSpace"):
            state["value"] = ""
            state["armed"] = False
            render(t("not set"))
            on_change("")
            return "break"
        if is_modifier_key(event.keycode):
            # Still on the way to a combination.
            return "break"
        try:
            state["value"] = from_event(event.state, event.keycode)
        except HotkeyError as exc:
            render(str(exc)[:28], RED)
            box.after(1800, disarm)
            return "break"
        state["armed"] = False
        render(state["value"])
        on_change(state["value"])
        return "break"

    box.bind("<Button-1>", arm, add="+")
    box.bind("<FocusIn>", arm, add="+")
    box.bind("<FocusOut>", disarm, add="+")
    box.bind("<KeyPress>", key, add="+")
    box.configure(state="readonly")
    return box


def safe_cfg(btn, text: str, fg_color) -> None:
    """Configure *btn* text + fg_color, swallowing TclError if destroyed."""
    try:
        btn.configure(text=text, fg_color=fg_color)
    except (tk.TclError, ValueError):
        pass


def bind_right_click_recursive(widget, callback) -> None:
    """Bind <Button-3> to *widget* and every descendant.

    Used so that right-clicking anywhere on a composite card (frame, label,
    button, etc.) reliably triggers the same context menu.
    """
    try:
        widget.bind("<Button-3>", callback, add="+")
        for child in widget.winfo_children():
            bind_right_click_recursive(child, callback)
    except (tk.TclError, AttributeError):
        pass


def add_color_strip(card, color_info: dict, *, width: int = 3,
                    x: int = 3, y: int = 6, relheight: float = 0.78):
    """Place a colored side-strip on *card* if the color preset has one.

    Returns True if a strip was placed, False if the color has no strip.
    """
    strip = color_info.get("strip")
    if not strip:
        return False
    ctk.CTkFrame(card, width=width, fg_color=strip,
                  corner_radius=2).place(x=x, y=y, relheight=relheight)
    return True


def sort_entries_pinned_first(entries: list[dict]) -> list[dict]:
    """Return *entries* sorted with pinned items first, then by title."""
    return sorted(
        entries,
        key=lambda e: (not e.get("pinned", False),
                        e.get("title", "").lower()))


# ─── Cheap Row Widgets ───────────────────────────────────────
# A CustomTkinter widget draws itself onto its own canvas with rounded
# corners. That is what makes it look right, and it costs 9x a plain
# tk.Label for a CTkLabel, 35x for a CTkButton and 46x for a CTkFrame.
# Everywhere else in the app that is a fine price to pay once. In the entry
# list it is paid 43 times per row, on every search keystroke, category
# switch, pin, edit and delete — which is why a twenty-entry vault took
# five seconds to repaint.
#
# These build the same row out of plain Tk. The colours have to be resolved
# for the active mode by hand, because a plain widget will not re-pick a
# (light, dark) pair on its own — so the list is repainted when the theme
# changes. `tools/benchmark_ui.py` measures the difference.


def row_frame(parent, bg, **pack_kwargs):
    """An invisible container inside a card.

    Its only job is to group widgets for `pack`, so there is nothing for a
    CTkFrame's canvas and rounded corners to draw.
    """
    frame = tk.Frame(parent, bg=resolve(bg), highlightthickness=0, bd=0)
    if pack_kwargs:
        frame.pack(**pack_kwargs)
    return frame


def row_label(parent, text, bg, fg, font=None, **pack_kwargs):
    """Static text inside a card."""
    label = tk.Label(parent, text=text, bg=resolve(bg), fg=resolve(fg),
                     font=font or ("Segoe UI", 9), bd=0,
                     highlightthickness=0)
    if pack_kwargs:
        label.pack(**pack_kwargs)
    return label


# --- Rounded pills, without CustomTkinter's price -------------
#
# The cards were rebuilt on plain Tk widgets because a CTkButton costs
# 25-35x a tk.Label, and the small buttons on them lost their rounded
# corners in the move. Three ways to get the corners back were measured:
#
#   CTkButton                     6.00 ms each   (what was removed)
#   CTkCanvas + CTk's DrawEngine  4.03 ms each
#   tk.Label + a cached pill      0.48 ms each   <- this one
#   tk.Label, square              0.42 ms each   (the baseline)
#
# So the shape costs 15% on top of a plain label rather than 14x it. The
# pill is a tk.PhotoImage drawn once per (size, colour) pair and reused;
# the label draws its text over it with `compound="center"`.
#
# The corners are antialiased here, in Python. Tk will not antialias a
# canvas polygon, and Pillow is not a dependency of this project - adding
# one to round six 24px buttons would be a poor trade, and it would grow
# the one-file exe for the same six buttons.

_PILL_CACHE: dict = {}
_PILL_FONTS: dict = {}
_PILL_TK = None          # the interpreter the caches above belong to
_SS = 4                  # supersampling, per axis, inside the corners


def _pill_reset_if_stale(widget) -> None:
    """Drop the caches when the Tk interpreter has been replaced.

    A PhotoImage belongs to the interpreter that created it. Tests build
    and destroy a root per module, so a cache surviving across roots would
    hand out images that raise as soon as they are drawn.
    """
    global _PILL_TK
    if widget.tk is not _PILL_TK:
        _PILL_CACHE.clear()
        _PILL_FONTS.clear()
        _PILL_TK = widget.tk


def pill_font(widget, spec):
    """A measuring font for *spec*, cached per interpreter."""
    _pill_reset_if_stale(widget)
    key = tuple(spec)
    if key not in _PILL_FONTS:
        _PILL_FONTS[key] = tkfont.Font(font=spec)
    return _PILL_FONTS[key]


def pill_image(widget, width, height, radius, fill, behind):
    """A rounded rectangle of *fill* on *behind*, as a cached PhotoImage.

    Both colours are baked in because a Tk image has no alpha channel:
    the corners have to be blended against whatever sits behind them,
    which is why the card colour is part of the cache key.
    """
    _pill_reset_if_stale(widget)
    width, height = max(int(width), 1), max(int(height), 1)
    fill, behind = resolve(fill), resolve(behind)
    key = (width, height, radius, fill, behind)
    cached = _PILL_CACHE.get(key)
    if cached is not None:
        return cached

    fr, fg_, fb = (c // 256 for c in widget.winfo_rgb(fill))
    br, bg_, bb = (c // 256 for c in widget.winfo_rgb(behind))
    solid = "#%02x%02x%02x" % (fr, fg_, fb)
    r = max(0, min(int(radius), width // 2, height // 2))

    # A corner pixel takes one of _SS*_SS+1 coverage values, so the blends
    # are worth computing once rather than per pixel.
    steps = _SS * _SS
    blend = ["#%02x%02x%02x" % (round(br + (fr - br) * i / steps),
                                round(bg_ + (fg_ - bg_) * i / steps),
                                round(bb + (fb - bb) * i / steps))
             for i in range(steps + 1)]

    rows = []
    for y in range(height):
        row = []
        cy = (r - 0.5 if y < r
              else (height - r - 0.5 if y >= height - r else None))
        for x in range(width):
            cx = (r - 0.5 if x < r
                  else (width - r - 0.5 if x >= width - r else None))
            if cx is None or cy is None:
                row.append(solid)
                continue
            hits = 0
            for sy in range(_SS):
                dy = y + (sy + 0.5) / _SS - 0.5 - cy
                for sx in range(_SS):
                    dx = x + (sx + 0.5) / _SS - 0.5 - cx
                    if dx * dx + dy * dy <= r * r:
                        hits += 1
            row.append(blend[hits])
        rows.append("{" + " ".join(row) + "}")

    image = tk.PhotoImage(master=widget, width=width, height=height)
    image.put(" ".join(rows))
    _PILL_CACHE[key] = image
    return image


def _wear_pill(label, text, fill) -> None:
    """Redraw *label* as a pill of *fill*, wide enough for *text*."""
    shape = label._pill
    font = pill_font(label, shape["font"])
    width = font.measure(text) + 2 * shape["padx"]
    try:
        label.configure(
            text=text,
            image=pill_image(label, width, shape["height"], shape["radius"],
                             fill, shape["behind"]))
    except tk.TclError:
        pass


def icon_button(parent, text, command, *, bg, hover, fg, behind=None,
                font=None, radius=6, cursor="hand2", **pack_kwargs):
    """A small rounded button, built from a label and a cached image.

    Kept from the CTkButton this replaced: the corner radius, the hover
    cue, the hand cursor, the click, and tooltips - `tip()` binds with
    ``add="+"``, so it layers on top of the hover bindings rather than
    replacing them.
    """
    font = font or ("Segoe UI Emoji", 10)
    if behind is None:
        try:
            behind = parent.cget("bg")
        except tk.TclError:
            behind = bg
    padx, pady = 6, 2
    height = pill_font(parent, font).metrics("linespace") + 2 * pady
    label = tk.Label(parent, compound="center", fg=resolve(fg), font=font,
                     bd=0, highlightthickness=0, cursor=cursor,
                     bg=resolve(behind))
    label._pill = {"font": font, "padx": padx, "height": height,
                   "radius": radius, "behind": behind,
                   "rest": bg, "hover": hover, "text": text,
                   "flashing": False}
    _wear_pill(label, text, bg)

    def enter(_event):
        if not label._pill["flashing"]:
            _wear_pill(label, label._pill["text"], label._pill["hover"])

    def leave(_event):
        if not label._pill["flashing"]:
            _wear_pill(label, label._pill["text"], label._pill["rest"])

    label.bind("<Enter>", enter, add="+")
    label.bind("<Leave>", leave, add="+")
    if command is not None:
        label.bind("<Button-1>", lambda _e: command(), add="+")
    if pack_kwargs:
        label.pack(**pack_kwargs)
    return label


def flash_button(btn, text, colour, after_ms=1000) -> None:
    """Briefly show *text* on *btn* in *colour*, then put it back.

    Handles both kinds of button this app has: a CTkButton swaps its
    `fg_color`, a pill label is redrawn. Reading `fg_color` off a plain
    label is what used to raise here, and because the raise landed after
    the copy but before the auto-clear was scheduled, the secret stayed
    on the clipboard until something else overwrote it.
    """
    if not hasattr(btn, "_pill"):
        try:
            original, fill = btn.cget("text"), btn.cget("fg_color")
            btn.configure(text=text, fg_color=resolve(colour))
        except (tk.TclError, ValueError):
            return
        btn.after(after_ms, lambda: safe_cfg(btn, original, fill))
        return

    original = btn._pill["text"]
    btn._pill["flashing"] = True
    _wear_pill(btn, text, colour)

    def restore():
        try:
            if not btn.winfo_exists():
                return
        except tk.TclError:
            return
        btn._pill["flashing"] = False
        _wear_pill(btn, original, btn._pill["rest"])

    try:
        btn.after(after_ms, restore)
    except tk.TclError:
        pass


# ─── Card Pool ───────────────────────────────────────────────
def card_signature(entry) -> tuple:
    """Everything a card draws, so a stale one can be spotted.

    Both lists render the same fields, so they share this. Miss one and an
    edit to it would leave the old text on screen — which is the only way
    a cache like this can go wrong, so it is deliberately generous: the
    password is here even though the card shows a fixed-width mask,
    because the card also holds the real value for the reveal button.
    """
    return (entry.get("title", ""), entry.get("username", ""),
            entry.get("password", ""), entry.get("url", ""),
            entry.get("category", ""), entry.get("notes", ""),
            entry.get("color", "default"),
            bool(entry.get("pinned", False)),
            entry.get("modified_at") or entry.get("created_at"))



class CardPool:
    """Row widgets kept between refreshes and re-packed, not rebuilt.

    Destroying and rebuilding a list of cards costs seconds; hiding and
    showing the same widgets costs a fraction of that, because
    ``pack_forget`` unmaps a widget without tearing it down. The catch is
    that this is a cache, and the failure mode of a cache is showing what
    is no longer true — so a card is reused only while its entry still
    renders identically, which *signature* decides.

    Both lists in the app use one of these. The logic lives here rather
    than in each of them because a second copy is a second place for the
    invalidation rules to drift.
    """

    def __init__(self, build, signature, **pack_options):
        """*build* makes a card for an entry and returns it *unpacked*.

        *signature* returns everything that card draws, so a change to any
        of it can be spotted. *pack_options* are how a visible card is
        packed, and are applied in the order cards are shown.
        """
        self._build = build
        self._signature = signature
        self._pack_options = pack_options
        self._cards: dict = {}
        self._signatures: dict = {}

    # A read-only mapping of entry id -> card. Enough for a caller — or a
    # test — to ask what is cached without being able to corrupt it.
    def __len__(self) -> int:
        return len(self._cards)

    def __contains__(self, entry_id) -> bool:
        return entry_id in self._cards

    def __iter__(self):
        return iter(self._cards)

    def __getitem__(self, entry_id):
        return self._cards[entry_id]

    def keys(self):
        return self._cards.keys()

    def values(self):
        return self._cards.values()

    def items(self):
        return self._cards.items()

    def get(self, entry_id):
        return self._cards.get(entry_id)

    def hide_all(self) -> None:
        """Unmap every card, ready for the matching ones to be shown."""
        for card in self._cards.values():
            try:
                card.pack_forget()
            except tk.TclError:
                pass

    def show(self, entry, entry_id):
        """Pack the card for *entry*, building or rebuilding as needed."""
        card = self._cards.get(entry_id) if entry_id else None
        signature = self._signature(entry)

        if card is not None:
            try:
                stale = (self._signatures.get(entry_id) != signature
                         or not card.winfo_exists())
            except tk.TclError:
                stale = True
            if stale:
                self._destroy(entry_id)
                card = None

        if card is None:
            card = self._build(entry)
            if entry_id:
                self._cards[entry_id] = card
                self._signatures[entry_id] = signature

        try:
            card.pack(**self._pack_options)
        except tk.TclError:
            pass
        return card

    def keep_only(self, entry_ids) -> None:
        """Destroy cards for entries that are gone from the data.

        A card for an entry that is merely filtered out is kept — the next
        keystroke may well bring it back.
        """
        for entry_id in [i for i in self._cards if i not in entry_ids]:
            self._destroy(entry_id)

    def clear(self) -> None:
        """Drop every card.

        Used when something outside the entries changes how a card looks —
        the appearance mode or the language — because these are plain Tk
        widgets that keep the colours and text they were built with.
        """
        for entry_id in list(self._cards):
            self._destroy(entry_id)

    def forget(self) -> None:
        """Drop the references without destroying anything.

        For when the parent has already been destroyed and the widgets
        went with it; touching them would only raise.
        """
        self._cards.clear()
        self._signatures.clear()

    def _destroy(self, entry_id) -> None:
        card = self._cards.pop(entry_id, None)
        self._signatures.pop(entry_id, None)
        if card is not None:
            try:
                card.destroy()
            except tk.TclError:
                pass


# ─── Dialog Chrome ───────────────────────────────────────────
def dialog_header(parent, title: str, *, icon: str | None = None,
                  subtitle: str | None = None, size: int = 16,
                  big_icon: bool = False, pady: tuple = (14, 6)):
    """Draw the standard dialog header and return its title label.

    Every dialog opened with one of these repeated the same three labels by
    hand, at a slightly different size each time. The label is returned
    because a few headers carry a live count.

    With *big_icon* the icon gets its own oversized line above the title,
    which is how the short confirmation dialogs present it.
    """
    # Translated here rather than at every call site: these helpers are
    # the single point every dialog's chrome passes through, and t() on an
    # already-translated string is a no-op.
    title = t(title)
    if subtitle is not None:
        subtitle = t(subtitle)
    if icon and big_icon:
        ctk.CTkLabel(parent, text=icon,
                      font=ctk.CTkFont(size=30)).pack(pady=(pady[0], 2))
        text = title
        title_pady = (0, 0)
    else:
        text = f"{icon}  {title}" if icon else title
        title_pady = pady if subtitle is None else (pady[0], 2)

    label = ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(family="Segoe UI", size=size, weight="bold"),
        text_color=TEXT_PRI)
    label.pack(pady=title_pady)
    if subtitle is not None:
        ctk.CTkLabel(
            parent, text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SEC, wraplength=310,
            justify="center").pack(padx=18, pady=(0, pady[1]))
    return label


def button_row(parent, buttons: list[dict], *, padx: int = 24,
               pady: tuple = (0, 0), height: int = 36):
    """Pack a row of dialog buttons and return them keyed by ``name``.

    Each spec takes ``text`` and ``command``, plus any of ``name`` (the key
    in the returned dict), ``side`` ("left"/"right", default "left"),
    ``fg_color``/``hover_color``/``text_color``, ``width``, and ``expand``.
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=padx, pady=pady)
    made: dict = {}
    for spec in buttons:
        expand = spec.get("expand", False)
        btn = ctk.CTkButton(
            row, text=t(spec["text"]), height=height,
            width=spec.get("width", 140),
            font=ctk.CTkFont(family="Segoe UI", size=spec.get("size", 13),
                              weight=spec.get("weight", "normal")),
            fg_color=spec.get("fg_color", BG_TERT),
            hover_color=spec.get("hover_color", CARD_HOVER),
            text_color=spec.get("text_color", TEXT_PRI),
            corner_radius=spec.get("corner_radius", 10),
            command=spec["command"])
        # "start"/"end" rather than left/right: a confirm row reads
        # Delete | Cancel in both directions.
        side = spec.get("side", "start")
        side = {"left": side_start(), "start": side_start(),
                "right": side_end(), "end": side_end()}.get(side, side)
        btn.pack(side=side, padx=spec.get("padx", 4),
                 fill="x" if expand else None, expand=expand)
        if spec.get("name"):
            made[spec["name"]] = btn
    return made


# ─── iOS Group / Field Helpers ───────────────────────────────
def ios_group(parent, title: str | None = None, compact: bool = False):
    wrapper = ctk.CTkFrame(parent, fg_color="transparent")
    wrapper.pack(fill="x", pady=(0, 4 if compact else 8))
    if title:
        ctk.CTkLabel(wrapper, text=t(title).upper(),
                      font=ctk.CTkFont(family="Segoe UI", size=10),
                      text_color=TEXT_SEC, anchor=anchor_start()).pack(
            anchor=anchor_start(), padx=14, pady=(0, 2))
    group = ctk.CTkFrame(wrapper, fg_color=BG_GROUP, corner_radius=10)
    group.pack(fill="x")
    return group


def ios_field(group, label: str, idx: int = 0, show: str = "",
              placeholder: str = "", value: str = "",
              height: int = 34, is_textbox: bool = False,
              ltr: bool = False):
    """*ltr* pins the input to left alignment for content that is always
    Latin — a URL reads from the wrong edge in a right-aligned form,
    because Tk has no bidi algorithm to reorder it."""
    label, placeholder = t(label), t(placeholder) if placeholder else ""
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72,
                  anchor=anchor_start()).pack(side=side_start())
    if is_textbox:
        tb = ctk.CTkTextbox(row, height=height,
                             font=ctk.CTkFont(family="Segoe UI", size=12),
                             fg_color=INPUT_BG, border_width=0,
                             corner_radius=6, text_color=TEXT_PRI)
        tb.pack(side=side_start(), fill="x", expand=True, padx=pad(4, 0))
        if value:
            tb.insert("1.0", value)
        return tb
    entry = ctk.CTkEntry(row, height=height,
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          placeholder_text=placeholder, text_color=TEXT_PRI,
                          **({"justify": ltr_justify()} if ltr else {}),
                          **({} if not show else {"show": show}))
    entry.pack(side=side_start(), fill="x", expand=True, padx=pad(4, 0))
    if value:
        entry.insert(0, value)
    return entry


def ios_combo(group, label: str, values: list[str], current: str, idx: int = 0):
    label = t(label)
    if idx > 0:
        ctk.CTkFrame(group, height=1, fg_color=SEPARATOR).pack(
            fill="x", padx=(46, 0))
    row = ctk.CTkFrame(group, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(4 if idx == 0 else 3, 4))
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
                  text_color=TEXT_PRI, width=72,
                  anchor=anchor_start()).pack(side=side_start())
    cb = ctk.CTkComboBox(row, values=values, height=30,
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color=INPUT_BG, border_width=0, corner_radius=6,
                          button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                          dropdown_fg_color=BG_SEC, text_color=TEXT_PRI,
                          dropdown_text_color=TEXT_PRI)
    cb.pack(side=side_start(), fill="x", expand=True, padx=pad(4, 0))
    if current:
        cb.set(current)
    return cb


# ─── Search Bar Widget ───────────────────────────────────────
def make_search_bar(parent, search_var, categories, on_category,
                    height: int = 32, width: int | None = None):
    frame = ctk.CTkFrame(parent, fg_color=BG_TERT, corner_radius=10,
                          height=height)
    if width:
        frame.configure(width=width)
    frame.pack_propagate(False)

    ctk.CTkLabel(frame, text="🔍", font=ctk.CTkFont(size=12), width=24,
                  text_color=TEXT_SEC).pack(side=side_start(),
                                            padx=pad(8, 0))

    entry = ctk.CTkEntry(frame, textvariable=search_var, height=height - 4,
                          placeholder_text=t("Search passwords..."),
                          font=ctk.CTkFont(family="Segoe UI", size=12),
                          fg_color="transparent", border_width=0,
                          text_color=TEXT_PRI, placeholder_text_color=TEXT_TERT)
    entry.pack(side=side_start(), fill="x", expand=True, padx=pad(2, 0))
    frame._entry = entry  # store reference for focus shortcut

    def show_cat_menu():
        menu = tk.Menu(frame, tearoff=0, **menu_style())
        menu.add_command(label=t("🗂️  All"),
                          command=lambda: on_category("All"))
        menu.add_separator()
        for cat in categories():
            emoji = cat_emoji(cat)
            menu.add_command(label=f"{emoji}  {cat}",
                              command=lambda c=cat: on_category(c))
        try:
            menu.post(frame.winfo_rootx() + frame.winfo_width() - 30,
                      frame.winfo_rooty() + frame.winfo_height())
        except tk.TclError:
            pass

    cat_btn = ctk.CTkButton(frame, text="▼", width=28, height=height - 6,
                              font=ctk.CTkFont(size=10), fg_color="transparent",
                              hover_color=TEXT_QUAT, corner_radius=6,
                              text_color=TEXT_SEC, command=show_cat_menu)
    cat_btn.pack(side=side_end(), padx=pad(0, 4))
    tip(cat_btn, t("Filter by category"))
    return frame



def collapsible_group(parent, title: str, *, open_now: bool = False,
                      summary=None, compact: bool = False):
    """An `ios_group` behind a header that opens and closes.

    Built for the entry dialog, where every feature so far arrived as one
    more group at the bottom: the four fields nearly every entry uses had
    become a minority of what was on screen.

    *summary* is called to describe what is set inside, and its result is
    shown on the header while the section is closed. That part is not
    decoration. A collapsed section whose settings are silently in force
    is worse than a long form — the user has to be able to see that
    something in there is doing something without opening it.

    This is a dialog widget, not a list one. It uses CustomTkinter freely
    because it is built once when a dialog opens; the entry cards are the
    hot path and stay on plain Tk.
    """
    wrapper = ctk.CTkFrame(parent, fg_color="transparent")
    wrapper.pack(fill="x", pady=(0, 4 if compact else 8))

    header = ctk.CTkFrame(wrapper, fg_color="transparent")
    header.pack(fill="x", padx=14, pady=(0, 2))

    state = {"open": bool(open_now)}
    arrow = ctk.CTkLabel(
        header, text="▾" if state["open"] else "▸", width=12,
        font=ctk.CTkFont(size=11), text_color=TEXT_SEC)
    arrow.pack(side=side_start())
    caption = ctk.CTkLabel(
        header, text=t(title).upper(),
        font=ctk.CTkFont(family="Segoe UI", size=10),
        text_color=TEXT_SEC, anchor=anchor_start())
    caption.pack(side=side_start(), padx=pad(4, 0))
    note = ctk.CTkLabel(
        header, text="", font=ctk.CTkFont(family="Segoe UI", size=10),
        text_color=TEXT_TERT, anchor=anchor_start())
    note.pack(side=side_start(), padx=pad(8, 0))

    group = ctk.CTkFrame(wrapper, fg_color=BG_GROUP, corner_radius=10)

    def refresh_note():
        text = ""
        if summary is not None and not state["open"]:
            try:
                text = summary() or ""
            except Exception:  # noqa: BLE001 - a summary must never
                # take the dialog down with it.
                text = ""
        note.configure(text=text)

    def apply():
        arrow.configure(text="▾" if state["open"] else "▸")
        if state["open"]:
            group.pack(fill="x")
        else:
            group.pack_forget()
        refresh_note()

    def toggle(_event=None):
        state["open"] = not state["open"]
        apply()

    for widget in (header, arrow, caption, note):
        widget.bind("<Button-1>", toggle, add="+")
        widget.configure(cursor="hand2")

    apply()
    group.refresh_summary = refresh_note
    group.is_open = lambda: state["open"]
    return group
