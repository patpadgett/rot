"""Small formatting helpers used by both the CLI and the TUI."""

from __future__ import annotations

import math


def clean_text(value: str) -> str:
    """Strip terminal escape/control characters from repository metadata."""
    return "".join(
        character if character.isprintable() or character in "\t " else "?"
        for character in value
    )


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{human_count(count)} {word}"


def human_count(value: int | float) -> str:
    number = float(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number < 1_000:
        if number.is_integer():
            return f"{sign}{int(number)}"
        return f"{sign}{number:.1f}"
    if number < 1_000_000:
        scaled, suffix = number / 1_000, "k"
    elif number < 1_000_000_000:
        scaled, suffix = number / 1_000_000, "m"
    else:
        scaled, suffix = number / 1_000_000_000, "b"
    if scaled >= 100:
        text = f"{scaled:.0f}"
    elif scaled >= 10:
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
    else:
        text = f"{scaled:.2f}".rstrip("0").rstrip(".")
    return f"{sign}{text}{suffix}"


def human_age(timestamp: float | None, now: float, *, long: bool = False) -> str:
    if timestamp is None:
        return "no history"
    seconds = max(0.0, now - timestamp)
    days = seconds / 86_400
    if days < 1:
        hours = max(1, int(seconds // 3_600))
        return f"{hours} hour{'s' if hours != 1 else ''} ago" if long else "now"
    if days < 2:
        return "yesterday" if long else "1d"
    if days < 45:
        n = int(days)
        return f"{n} days ago" if long else f"{n}d"
    if days < 365:
        n = max(2, int(days // 30))
        return f"{n} months ago" if long else f"{n}mo"
    years = days / 365
    if years >= 10:
        text = f"{years:.0f}"
    else:
        text = f"{years:.1f}".rstrip("0").rstrip(".")
    return f"{text} years ago" if long else f"{text}y"


def age_days(timestamp: float | None, now: float) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp) / 86_400)


def shorten_middle(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    keep = width - 1
    left = (keep + 1) // 2
    right = keep - left
    return f"{text[:left]}…{text[-right:]}" if right else f"{text[:width - 1]}…"


def shorten_end(text: str, width: int) -> str:
    """Truncate at the end. Better for identifiers than middle truncation."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return f"{text[: width - 1]}…"


def shorten_path(path: str, width: int) -> str:
    """Keep the filename and as much of the directory as will fit."""
    if len(path) <= width:
        return path
    name = path.rsplit("/", 1)[-1]
    if len(name) >= width:
        return shorten_middle(name, width)
    room = width - len(name) - 2
    head = path[: max(0, room)]
    return f"{head}…/{name}" if head else f"…/{name}"


def bar(ratio: float, width: int, *, full: str = "█", empty: str = "░") -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    if filled == 0 and ratio > 0:
        filled = 1
    return full * filled + empty * max(0, width - filled)


def criticality(value: float) -> str:
    if value >= 72:
        return "critical"
    if value >= 54:
        return "high"
    if value >= 34:
        return "medium"
    if value >= 18:
        return "low"
    return "calm"


def duration_ms(seconds: float) -> str:
    milliseconds = seconds * 1_000
    if milliseconds < 10:
        return f"{milliseconds:.1f} ms"
    if milliseconds < 1_000:
        return f"{milliseconds:.0f} ms"
    return f"{milliseconds / 1_000:.2f} s"


def log_scale(value: float, ceiling: float) -> float:
    if value <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log1p(value) / math.log1p(ceiling)))
