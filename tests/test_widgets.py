"""Treemap geometry and tile label fallbacks."""

from __future__ import annotations

import pytest

from rot.models import FileMetric
from rot.widgets import Treemap, _MapItem, _strip_layout

NOW = 1_750_000_000.0
DAY = 86_400.0


def make_item(path: str, weight: float) -> _MapItem:
    return _MapItem(
        path=path,
        label=path,
        weight=weight,
        value=0.5,
        color="#5a8f4a",
        file=None,
    )


def test_strip_layout_preserves_area_and_bounds():
    items = [make_item(f"src/file{index}.py", index) for index in range(1, 16)]
    placed = _strip_layout(items, 0.0, 0.0, 100.0, 20.0)
    assert len(placed) == 15
    assert {tile.item.path for tile in placed} == {item.path for item in items}
    total_area = sum(tile.width * tile.height for tile in placed)
    assert total_area == pytest.approx(2_000.0)
    assert all(0 <= tile.x <= 100 for tile in placed)
    assert all(0 <= tile.y <= 20 for tile in placed)
    assert all(tile.x + tile.width <= 100.0001 for tile in placed)
    assert all(tile.y + tile.height <= 20.0001 for tile in placed)
    # The 15 items form three bands, and each tile's area is proportional to
    # its weight except where rounding to terminal cells slightly distorts it.
    assert len({round(tile.y, 6) for tile in placed}) == 3
    assert placed[0].width * placed[0].height == pytest.approx(2_000 * 1 / 120)
    assert placed[-1].width * placed[-1].height == pytest.approx(2_000 * 15 / 120)


def test_strip_layout_uses_one_band_for_short_or_small_maps():
    two = [make_item("a.py", 1), make_item("b.py", 2)]
    placed = _strip_layout(two, 0.0, 0.0, 40.0, 2.0)
    assert len(placed) == 2
    assert len({tile.y for tile in placed}) == 1
    assert sum(tile.width for tile in placed) == pytest.approx(40.0)

    six = [make_item(f"{index}.py", 1) for index in range(6)]
    short = _strip_layout(six, 0.0, 0.0, 60.0, 2.0)
    assert len({tile.y for tile in short}) == 1


def test_strip_layout_handles_empty_and_zero_weights():
    assert _strip_layout([], 0, 0, 100, 10) == []
    assert _strip_layout([make_item("a.py", 1)], 0, 0, 0, 10) == []
    placed = _strip_layout(
        [make_item("a.py", 0), make_item("b.py", 0)], 5.0, 2.0, 50.0, 8.0
    )
    assert len(placed) == 2
    assert placed[0].x == 5.0
    assert placed[0].y == 2.0
    assert placed[-1].x + placed[-1].width == pytest.approx(55.0)


def test_tile_label_prefers_path_then_name_then_stem():
    treemap = Treemap()
    file = FileMetric(
        path="lib/legacy/tax_calc.py",
        language="python",
        risk=88,
        commits=12,
        max_complexity=15,
        sloc=350,
        last_commit=NOW - 500 * DAY,
    )
    assert treemap._tile_label(file, 40) == "lib/legacy/tax_calc.py"
    assert treemap._tile_label(file, 12) == "tax_calc.py"
    assert treemap._tile_label(file, 8) == "tax_calc"
    assert treemap._tile_label(file, 4) == "tax…"
    assert treemap._tile_label(file, 0) == ""


def test_best_detail_falls_back_without_overflowing():
    treemap = Treemap()
    file = FileMetric(
        path="lib/legacy/tax_calc.py",
        language="python",
        risk=88,
        commits=12,
        max_complexity=15,
        sloc=350,
        last_commit=NOW - 500 * DAY,
    )

    treemap.set_mode("risk")
    assert treemap._best_detail(file, 40) == "risk 88 · 12 touches"
    assert treemap._best_detail(file, 15) == "risk 88 · 12×"
    assert treemap._best_detail(file, 5) == "r88"
    assert treemap._best_detail(file, 2) == ""

    treemap.set_mode("complexity")
    assert treemap._best_detail(file, 5) == "CC 15"
    assert treemap._best_detail(file, 4) == "CC15"

    treemap.set_mode("churn")
    assert treemap._best_detail(file, 30) == "12 touches · 0 changed"
    assert treemap._best_detail(file, 5) == "12×"

    treemap.set_mode("age")
    treemap.now = NOW
    assert "idle" in treemap._best_detail(file, 30)
    assert treemap._best_detail(file, 9) == "idle 1.4y"
