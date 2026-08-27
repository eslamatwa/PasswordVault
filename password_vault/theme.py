"""
UI theme constants — Apple-style light and dark palettes, plus card presets.

Every color is a ``(light, dark)`` pair, which is exactly the form
CustomTkinter accepts for widget colors: it picks the element matching the
active appearance mode and re-picks it when the mode changes, so switching
theme needs no per-widget work.

Raw tkinter widgets (menus, canvases, tooltips) only understand a single
color string. Those call sites must resolve the pair at creation time with
:func:`resolve`, or use :func:`menu_style` for menus.
"""

from __future__ import annotations

import customtkinter as ctk

Color = tuple[str, str]

# ─── Category Emoji Map ──────────────────────────────────────
CAT_EMOJIS: dict[str, str] = {
    "General": "📂", "Social": "💬", "Work": "💼", "Banking": "🏦",
    "Gaming": "🎮", "Shopping": "🛒", "Email": "📧", "Cloud": "☁️",
    "VPN": "🔒", "Server": "🖥️", "Database": "🗄️", "API": "🔗", "Other": "📌",
}
DEFAULT_EMOJI = "📁"

# ─── Colors ──────────────────────────────────────────────────
#                     light        dark
BG: Color =          ("#f2f2f7", "#1c1c1e")
BG_SEC: Color =      ("#ffffff", "#2c2c2e")
BG_TERT: Color =     ("#e5e5ea", "#3a3a3c")
BG_GROUP: Color =    ("#ffffff", "#2c2c2e")
SEPARATOR: Color =   ("#d1d1d6", "#38383a")

ACCENT: Color =       ("#007aff", "#0a84ff")
ACCENT_HOVER: Color = ("#0062cc", "#0070e0")
GREEN: Color =        ("#34c759", "#30d158")
GREEN_HOVER: Color =  ("#2aa147", "#28b84c")
RED: Color =          ("#ff3b30", "#ff453a")
RED_HOVER: Color =    ("#d92f26", "#e03e35")
ORANGE: Color =       ("#ff9500", "#ff9f0a")
ORANGE_HOVER: Color = ("#d97e00", "#e08e09")
YELLOW: Color =       ("#e6b800", "#ffd60a")
TEAL: Color =         ("#0a9fd8", "#64d2ff")
PURPLE: Color =       ("#af52de", "#bf5af2")
PURPLE_HOVER: Color = ("#9440bd", "#a04ad0")

TEXT_PRI: Color =  ("#000000", "#ffffff")
TEXT_SEC: Color =  ("#6c6c70", "#8e8e93")
TEXT_TERT: Color = ("#8e8e93", "#636366")
TEXT_QUAT: Color = ("#b0b0b5", "#48484a")

# Text drawn on top of an accent fill, where the surface color is the same
# in both modes.
TEXT_ON_ACCENT: Color = ("#ffffff", "#ffffff")
# Green fills are light in both modes, so their label stays dark.
TEXT_ON_GREEN: Color = ("#0d2b16", "#0d2b16")

# Tinted panels behind a warning or an informational note.
WARN_BG: Color = ("#fdf1e3", "#3a2a20")
INFO_BG: Color = ("#e8f0fe", "#22283a")

BADGE_BG: Color =    ("#e5e5ea", "#3a3a3c")
INPUT_BG: Color =    ("#ffffff", "#1c1c1e")
CARD_HOVER: Color =  ("#e5e5ea", "#3a3a3c")
SIDEBAR_BG: Color =  ("#ffffff", "#2c2c2e")
SIDEBAR_SEL: Color = ("#007aff", "#0a84ff")

# Tooltips stay a dark bubble in both modes, like the system ones.
TT_BG: Color = ("#3a3a3c", "#48484a")
TT_FG: Color = ("#ffffff", "#ffffff")

# ─── Card Color Presets (subtle tints) ───────────────────────
# The strip is a (light, dark) pair like every other color here. It used to
# be one value tuned against a dark card, so in light mode the accent sat on
# a pale tint at nearly the same luminance and the strip read as a bright
# smear rather than an edge. The light values are the darker, more saturated
# member of each iOS pair; the dark values are the originals.
CARD_COLORS: dict[str, dict] = {
    "default": {"bg": ("#ffffff", "#2c2c2e"), "strip": None,
                "label": "Default"},
    "blue":    {"bg": ("#e8f0fe", "#22283a"),
                "strip": ("#0062cc", "#0a84ff"), "label": "Blue"},
    "green":   {"bg": ("#e6f7ec", "#222e26"),
                "strip": ("#248a3d", "#30d158"), "label": "Green"},
    "red":     {"bg": ("#fdebea", "#2e2426"),
                "strip": ("#d70015", "#ff453a"), "label": "Red"},
    "orange":  {"bg": ("#fdf1e3", "#2e2a24"),
                "strip": ("#c93400", "#ff9f0a"), "label": "Orange"},
    "purple":  {"bg": ("#f4eafc", "#28242e"),
                "strip": ("#8944ab", "#bf5af2"), "label": "Purple"},
    "teal":    {"bg": ("#e6f6fd", "#22282e"),
                "strip": ("#0071a4", "#64d2ff"), "label": "Teal"},
    "yellow":  {"bg": ("#fdf8e0", "#2e2d22"),
                "strip": ("#a05a00", "#ffd60a"), "label": "Yellow"},
    "pink":    {"bg": ("#fdeaee", "#2e2428"),
                "strip": ("#d30f45", "#ff6482"), "label": "Pink"},
}

def resolve(color) -> str:
    """Return the single color string for the active appearance mode."""
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def menu_style(font: tuple = ("Segoe UI", 10)) -> dict:
    """Resolved keyword arguments for a raw ``tk.Menu``."""
    return {
        "bg": resolve(BG_SEC),
        "fg": resolve(TEXT_PRI),
        "activebackground": resolve(ACCENT),
        "activeforeground": resolve(TEXT_ON_ACCENT),
        "font": font,
    }


def cat_emoji(name: str) -> str:
    """Return the emoji for a category name."""
    return CAT_EMOJIS.get(name, DEFAULT_EMOJI)
