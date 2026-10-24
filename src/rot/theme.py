"""Colour system shared by the widgets, modals, and Rich exporters."""

from __future__ import annotations

BACKGROUND = "#070c09"
SURFACE = "#0a110d"
PANEL = "#0e1712"
PANEL_RAISED = "#132019"
BORDER = "#22362a"
BORDER_BRIGHT = "#497451"
TEXT = "#d9e8de"
MUTED = "#7d9588"
DIM = "#4a6456"
ACCENT = "#b8f36b"
TEAL = "#4de3c1"
BLUE = "#67b7ff"
YELLOW = "#f5d76e"
ORANGE = "#ff9f43"
RED = "#ff5f73"
PINK = "#f26db6"
PURPLE = "#c792ea"
GRID_LINE = "#1a2a20"

GRADE_COLORS = {
    "critical": RED,
    "high": ORANGE,
    "medium": YELLOW,
    "low": TEAL,
    "calm": "#76b88d",
    "healthy": "#76b88d",
}

MODE_TITLES = {
    "risk": "RISK",
    "churn": "CHURN",
    "age": "CODE ROT",
    "complexity": "COMPLEXITY",
}

MODE_HELP = {
    "risk": "total rot score",
    "churn": "history pressure",
    "age": "time since last touch",
    "complexity": "structural weight",
}

MAP_RAMPS: dict[str, list[str]] = {
    "risk": ["#14453a", "#23603e", "#5d712a", "#9a681f", "#bb432e", "#dc2c4a"],
    "churn": ["#103c49", "#1c5d68", "#4d5c8f", "#8a408e", "#c72d78", "#ee3b71"],
    "age": ["#104b45", "#2e6b4d", "#796f2a", "#a85e26", "#b4462b", "#7a2c41"],
    "complexity": ["#153b4f", "#1f5b63", "#5f7030", "#a36b1f", "#c4472b", "#de3348"],
}

LANGUAGE_COLORS = {
    "python": "#ffd166",
    "javascript": "#f4e04d",
    "typescript": "#6ab7ff",
    "go": "#4dd8cf",
    "rust": "#ff9d6c",
    "java": "#f89820",
    "kotlin": "#a78bfa",
    "c": "#9cc2f5",
    "cpp": "#8fb4ff",
    "csharp": "#a78bfa",
    "ruby": "#ff6b7d",
    "php": "#9aa5ff",
    "swift": "#ff9f6e",
    "scala": "#ff6d6d",
    "shell": "#84d68a",
    "lua": "#7a9cff",
    "sql": "#f2b36b",
    "vue": "#56d6a0",
    "svelte": "#ff7b5c",
    "dart": "#58c7f3",
    "elixir": "#b58cff",
    "haskell": "#b794f4",
    "zig": "#f6c344",
}

_SEVERITY = {
    "critical": RED,
    "high": ORANGE,
    "medium": YELLOW,
    "low": TEAL,
    "calm": "#76b88d",
}


def grade_color(grade: str) -> str:
    return GRADE_COLORS.get(grade, TEXT)


def severity_color(severity: float) -> str:
    if severity >= 0.78:
        return RED
    if severity >= 0.52:
        return ORANGE
    if severity >= 0.3:
        return YELLOW
    return TEAL


def language_color(language: str) -> str:
    return LANGUAGE_COLORS.get(language, MUTED)


def _hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_hex(red: float, green: float, blue: float) -> str:
    return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"


def mix(color_a: str, color_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    a = _hex_rgb(color_a)
    b = _hex_rgb(color_b)
    return _rgb_hex(
        a[0] + (b[0] - a[0]) * ratio,
        a[1] + (b[1] - a[1]) * ratio,
        a[2] + (b[2] - a[2]) * ratio,
    )


def map_color(mode: str, value: float) -> str:
    ramp = MAP_RAMPS.get(mode, MAP_RAMPS["risk"])
    value = max(0.0, min(1.0, value))
    position = value * (len(ramp) - 1)
    low = int(position)
    high = min(len(ramp) - 1, low + 1)
    return mix(ramp[low], ramp[high], position - low)


def brighter(color: str, amount: float = 0.18) -> str:
    return mix(color, "#ffffff", amount)


def contrast_text(color: str) -> str:
    red, green, blue = _hex_rgb(color)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#07100b" if luminance > 0.6 else "#f4fbf6"
