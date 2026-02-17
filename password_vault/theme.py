"""
UI theme constants — Apple Dark Mode palette and card presets.
"""

# ─── Category Emoji Map ──────────────────────────────────────
CAT_EMOJIS: dict[str, str] = {
    "General": "📂", "Social": "💬", "Work": "💼", "Banking": "🏦",
    "Gaming": "🎮", "Shopping": "🛒", "Email": "📧", "Cloud": "☁️",
    "VPN": "🔒", "Server": "🖥️", "Database": "🗄️", "API": "🔗", "Other": "📌",
}
DEFAULT_EMOJI = "📁"

# ─── Card Color Presets (subtle tints) ───────────────────────
CARD_COLORS: dict[str, dict] = {
    "default": {"bg": "#2c2c2e", "strip": None,      "label": "Default"},
    "blue":    {"bg": "#22283a", "strip": "#0a84ff",  "label": "Blue"},
    "green":   {"bg": "#222e26", "strip": "#30d158",  "label": "Green"},
    "red":     {"bg": "#2e2426", "strip": "#ff453a",  "label": "Red"},
    "orange":  {"bg": "#2e2a24", "strip": "#ff9f0a",  "label": "Orange"},
    "purple":  {"bg": "#28242e", "strip": "#bf5af2",  "label": "Purple"},
    "teal":    {"bg": "#22282e", "strip": "#64d2ff",  "label": "Teal"},
    "yellow":  {"bg": "#2e2d22", "strip": "#ffd60a",  "label": "Yellow"},
    "pink":    {"bg": "#2e2428", "strip": "#ff6482",  "label": "Pink"},
}

# ─── Colors (Apple Dark Mode) ────────────────────────────────
BG          = "#1c1c1e"
BG_SEC      = "#2c2c2e"
BG_TERT     = "#3a3a3c"
BG_GROUP    = "#2c2c2e"
SEPARATOR   = "#38383a"

ACCENT      = "#0a84ff"
ACCENT_HOVER = "#0070e0"
GREEN       = "#30d158"
GREEN_HOVER = "#28b84c"
RED         = "#ff453a"
RED_HOVER   = "#e03e35"
ORANGE      = "#ff9f0a"
ORANGE_HOVER = "#e08e09"
YELLOW      = "#ffd60a"
TEAL        = "#64d2ff"
PURPLE      = "#bf5af2"

TEXT_PRI    = "#ffffff"
TEXT_SEC    = "#8e8e93"
TEXT_TERT   = "#636366"
TEXT_QUAT   = "#48484a"

BADGE_BG    = "#3a3a3c"
INPUT_BG    = "#1c1c1e"
CARD_HOVER  = "#3a3a3c"
SIDEBAR_BG  = "#2c2c2e"
SIDEBAR_SEL = "#0a84ff"

TT_BG       = "#48484a"
TT_FG       = "#ffffff"


def cat_emoji(name: str) -> str:
    """Return the emoji for a category name."""
    return CAT_EMOJIS.get(name, DEFAULT_EMOJI)

