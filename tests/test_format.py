"""Formatting helpers should stay compact, predictable, and safe."""

from __future__ import annotations

from rot.format import (
    bar,
    clean_text,
    criticality,
    duration_ms,
    human_age,
    human_count,
    log_scale,
    plural,
    shorten_end,
    shorten_middle,
    shorten_path,
)

NOW = 1_750_000_000.0
DAY = 86_400.0


def test_clean_text_keeps_unicode_but_replaces_controls():
    assert clean_text("café\tcode\n") == "café\tcode?"
    assert clean_text("a\x00b\x1fc") == "a?b?c"
    assert clean_text("\x1b[31mred\x1b[0m") == "?[31mred?[0m"


def test_human_count_and_plural():
    assert human_count(999) == "999"
    assert human_count(1_500) == "1.5k"
    assert human_count(23_400) == "23.4k"
    assert plural(1, "file") == "1 file"
    assert plural(2, "file") == "2 files"
    assert plural(2, "match", "matches") == "2 matches"


def test_human_age_short_and_long():
    assert human_age(None, NOW) == "no history"
    assert human_age(NOW - 10 * DAY, NOW) == "10d"
    assert human_age(NOW - 60 * DAY, NOW) == "2mo"
    assert human_age(NOW - 800 * DAY, NOW) == "2.2y"
    assert human_age(NOW - 800 * DAY, NOW, long=True) == "2.2 years ago"
    assert human_age(NOW + 2 * DAY, NOW) == "now"


def test_shorteners_respect_width():
    assert shorten_middle("abcdefghij", 7) == "abc…hij"
    assert shorten_end("abcdefghij", 7) == "abcdef…"
    assert shorten_end("short", 10) == "short"
    assert shorten_path("src/very/long/module.py", 18).startswith("src/")
    assert len(shorten_path("src/very/long/module.py", 18)) <= 18


def test_bar_criticality_and_duration():
    assert bar(0.5, 10) == "█████░░░░░"
    assert bar(2.0, 4) == "████"
    assert criticality(0) == "calm"
    assert criticality(25) == "low"
    assert criticality(45) == "medium"
    assert criticality(65) == "high"
    assert criticality(90) == "critical"
    assert duration_ms(0.084) == "84 ms"
    assert duration_ms(12.0) == "12.00 s"


def test_log_scale_is_bounded():
    assert log_scale(0, 100) == 0.0
    assert log_scale(100, 100) == 1.0
    assert 0 < log_scale(10, 100) < 1
