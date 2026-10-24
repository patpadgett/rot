"""Custom Textual widgets: the brand bar, metric cards, and entropy map."""

from __future__ import annotations

from dataclasses import dataclass

from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.message import Message
from textual.widget import Widget

from . import __version__
from .analyze import language_label
from .format import (
    bar,
    clean_text,
    human_age,
    human_count,
    shorten_end,
    shorten_middle,
    shorten_path,
)
from .models import FileMetric, RepoSummary, Snapshot
from .theme import (
    ACCENT,
    BACKGROUND,
    BORDER,
    DIM,
    GRID_LINE,
    MAP_RAMPS,
    MODE_HELP,
    MODE_TITLES,
    MUTED,
    ORANGE,
    PINK,
    RED,
    TEAL,
    TEXT,
    YELLOW,
    brighter,
    contrast_text,
    grade_color,
    language_color,
    map_color,
    mix,
)

_LOGO_TOP = "█▀█ █▀█ ▀█▀"
_LOGO_BOTTOM = "█▀▄ █▄█  █"
_LOGO_COLORS = (ACCENT, "#d7e96a", ORANGE)
_LOGO_COLORS_DARK = ("#6f9746", "#7b8844", "#a66334")


def _logo(top: bool) -> Text:
    source = _LOGO_TOP if top else _LOGO_BOTTOM
    colors = _LOGO_COLORS if top else _LOGO_COLORS_DARK
    text = Text()
    for index, color in enumerate(colors):
        start = index * 4
        text.append(source[start : start + 4], style=f"bold {color}")
    return text


class BrandBar(Widget):
    """A custom masthead with the repo identity and scan cost."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.snapshot: Snapshot | None = None
        self.scanning = False

    def set_snapshot(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.refresh()

    def set_scanning(self, scanning: bool) -> None:
        self.scanning = scanning
        self.refresh()

    def render(self) -> Table:
        if self.snapshot is None:
            return Text(" rot · waiting for scan", style=MUTED)

        summary = self.snapshot.summary
        left = Table.grid(padding=(0, 0))
        left.add_column(no_wrap=True, overflow="ellipsis")
        top = _logo(True)
        top.append("  ")
        top.append("CODEBASE ENTROPY", style=f"bold {TEXT}")
        bottom = _logo(False)
        bottom.append("  ")
        bottom.append("health & risk inspector", style=MUTED)
        meta = Text("             ", style=DIM)
        meta.append(f"v{__version__}", style=DIM)
        meta.append("  ·  offline git + AST", style=DIM)
        left.add_row(top)
        left.add_row(bottom)
        left.add_row(meta)

        right = Table.grid(padding=(0, 0))
        right.add_column(justify="right", no_wrap=True, overflow="ellipsis")
        repo = Text()
        repo.append("● ", style=ACCENT)
        repo.append(f"{clean_text(summary.name)}", style=f"bold {TEXT}")
        repo.append("  ")
        repo.append(f" {clean_text(summary.branch)} ", style=f"bold {BACKGROUND} on {ACCENT}")
        right.add_row(repo)
        facts = Text()
        facts.append(f"HEAD {summary.head}", style=MUTED)
        facts.append("  ·  ", style=DIM)
        facts.append(f"{human_count(summary.commits)} commits", style=MUTED)
        facts.append("  ·  ", style=DIM)
        facts.append(f"{summary.authors} authors", style=MUTED)
        right.add_row(facts)
        scan = Text()
        if self.scanning:
            scan.append("rescanning repository …", style=YELLOW)
        else:
            speed_color = TEAL if summary.scan_ms < 250 else YELLOW if summary.scan_ms < 900 else ORANGE
            scan.append(f"scanned offline in {summary.scan_ms:.0f} ms", style=speed_color)
            if summary.warnings:
                scan.append(f"  ·  {len(summary.warnings)} note{'s' if len(summary.warnings) != 1 else ''}", style=YELLOW)
        right.add_row(scan)

        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True, overflow="ellipsis")
        grid.add_row(left, right)
        return grid


class MetricCard(Widget):
    """One compact, colored metric tile."""

    def __init__(self, heading: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.heading = heading
        self.value = "—"
        self.badge = ""
        self.subtitle = ""
        self.ratio = 0.0
        self.value_color = TEXT

    def set_metric(
        self,
        value: str,
        *,
        badge: str = "",
        subtitle: str = "",
        ratio: float = 0.0,
        color: str = TEXT,
    ) -> None:
        self.value = value
        self.badge = badge
        self.subtitle = subtitle
        self.ratio = max(0.0, min(1.0, ratio))
        self.value_color = color
        self.refresh()

    def render(self) -> Text:
        width = max(8, self.content_size.width)
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(self.heading.upper(), style=f"bold {MUTED}")
        text.append("\n")
        text.append(self.value, style=f"bold {self.value_color}")
        if self.badge:
            text.append("  ")
            text.append(self.badge.upper(), style=f"bold {self.value_color}")
        text.append("\n")
        bar_width = max(4, min(width - 1, 28))
        text.append(bar(self.ratio, bar_width), style=self.value_color)
        text.append("\n")
        text.append(shorten_middle(self.subtitle, width), style=DIM)
        return text


class _MapItem:
    __slots__ = ("path", "label", "weight", "value", "color", "file", "note")

    def __init__(
        self,
        *,
        path: str | None,
        label: str,
        weight: float,
        value: float,
        color: str,
        file: FileMetric | None,
        note: str = "",
    ) -> None:
        self.path = path
        self.label = label
        self.weight = weight
        self.value = value
        self.color = color
        self.file = file
        self.note = note


@dataclass(slots=True)
class _Placed:
    item: _MapItem
    x: float
    y: float
    width: float
    height: float


def _strip_layout(
    items: list[_MapItem],
    x: float,
    y: float,
    width: float,
    height: float,
) -> list[_Placed]:
    """Lay out area-proportional tiles in a few horizontal bands.

    A classic squarified pass turns a wide, short dashboard map into a row of
    hair-thin columns.  Banding the sorted items into two or three rows keeps
    every tile wide enough for a filename while preserving exact area
    proportions: row height is proportional to row mass, and each tile's width
    is proportional to its mass within that row.
    """
    if not items or width <= 1 or height <= 0:
        return []

    weights = [max(0.0, item.weight) for item in items]
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(items)
        total = float(len(items))

    rows = 1
    if len(items) >= 6 and height >= 3:
        rows = 2
    if len(items) >= 15 and height >= 13:
        rows = 3

    remaining = len(items)
    cursor_y = y
    cursor_item = 0
    placed: list[_Placed] = []
    for row in range(rows):
        if remaining <= 0:
            break
        rows_left = rows - row
        count = (remaining + rows_left - 1) // rows_left
        group = items[cursor_item : cursor_item + count]
        group_weights = weights[cursor_item : cursor_item + count]
        cursor_item += count
        remaining -= count

        row_mass = sum(group_weights)
        if row_mass <= 0:
            continue
        row_height = height * row_mass / total
        if row == rows - 1:
            row_height = y + height - cursor_y
        elif row_height < 1:
            row_height = 1.0

        cursor_x = x
        for index, (item, weight) in enumerate(zip(group, group_weights)):
            if index == len(group) - 1:
                tile_width = x + width - cursor_x
            else:
                tile_width = width * weight / row_mass
            if tile_width <= 0:
                continue
            placed.append(_Placed(item, cursor_x, cursor_y, tile_width, row_height))
            cursor_x += tile_width
        cursor_y += row_height
    return placed


class Treemap(Widget):
    """An interactive, area-proportional treemap rendered with terminal cells."""

    class TileClicked(Message):
        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    MODES = ("risk", "churn", "age", "complexity")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.files: list[FileMetric] = []
        self.mode = "risk"
        self.selected_path: str | None = None
        self.now = 0.0
        self._hitboxes: list[tuple[int, int, int, int, str | None]] = []
        self._update_border()

    def set_data(
        self,
        files: list[FileMetric],
        *,
        selected_path: str | None,
        now: float,
    ) -> None:
        self.files = files
        self.selected_path = selected_path
        self.now = now
        self._update_border()
        self.refresh()

    def set_selected(self, path: str | None) -> None:
        self.selected_path = path
        self.refresh()

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in self.MODES else "risk"
        self._update_border()
        self.refresh()

    def _update_border(self) -> None:
        title = MODE_TITLES.get(self.mode, self.mode.upper())
        self.border_title = f" ENTROPY MAP · {title} "
        total = len(self.files)
        if total:
            shown = min(total, 40)
            aggregate = total - shown
            subtitle = f" area ∝ LOC · {shown} shown"
            if aggregate:
                subtitle += f" + {aggregate} rolled up"
            subtitle += " · c to recolor "
            self.border_subtitle = subtitle
        else:
            self.border_subtitle = " no files "

    def _value_and_color(self, file: FileMetric) -> tuple[float, str]:
        if self.mode == "churn":
            value = file.churn_score / 100
        elif self.mode == "age":
            if file.last_commit is None:
                value = 0.08
            else:
                age_days = max(0.0, (self.now - file.last_commit) / 86_400)
                value = min(1.0, age_days / 1_460)
        elif self.mode == "complexity":
            value = file.complexity_score / 100
        else:
            value = file.risk / 100
        return value, map_color(self.mode, value)

    def _items(self) -> list[_MapItem]:
        if not self.files:
            return []
        width = max(30, self.content_size.width)
        # Roughly one tile per 12 cells keeps labels readable.  The tail rolls
        # into a single aggregate tile rather than becoming unreadable slivers.
        limit = min(40, max(10, 2 * (width // 12)))
        ordered = sorted(
            self.files,
            key=lambda file: max(file.sloc, 5),
            reverse=True,
        )
        chosen = ordered[:limit]
        chosen_paths = {file.path for file in chosen}
        if self.selected_path and self.selected_path not in chosen_paths:
            selected_file = next(
                (file for file in ordered if file.path == self.selected_path), None
            )
            if selected_file is not None:
                chosen = chosen[:-1] + [selected_file]
                chosen_paths = {file.path for file in chosen}
        remaining = [file for file in ordered if file.path not in chosen_paths]
        items: list[_MapItem] = []
        for file in chosen:
            value, color = self._value_and_color(file)
            items.append(
                _MapItem(
                    path=file.path,
                    label=file.filename,
                    weight=float(max(file.sloc, 10)),
                    value=value,
                    color=color,
                    file=file,
                )
            )
        if remaining:
            weight = sum(max(file.sloc, 10) for file in remaining)
            values = [self._value_and_color(file)[0] for file in remaining]
            value = (
                sum(
                    lens * max(file.sloc, 10)
                    for lens, file in zip(values, remaining)
                )
                / weight
                if weight
                else 0.0
            )
            avg_risk = (
                sum(file.risk * max(file.sloc, 10) for file in remaining) / weight
                if weight
                else 0.0
            )
            items.append(
                _MapItem(
                    path=None,
                    label=f"+{len(remaining)} files",
                    weight=float(weight),
                    value=value,
                    color=mix(map_color(self.mode, value), "#1d2c22", 0.28),
                    file=None,
                    note=f"avg risk {avg_risk:.0f}",
                )
            )
        return items

    def _tile_label(self, file: FileMetric, width: int) -> str:
        if width <= 0:
            return ""
        path = clean_text(file.path)
        name = clean_text(file.filename)
        stem = name.rsplit(".", 1)[0]
        candidates: list[str] = []
        if width >= 26:
            candidates.append(shorten_path(path, width))
        candidates.extend([name, stem])
        for candidate in candidates:
            if candidate and len(candidate) <= width:
                return candidate
        return shorten_end(stem or name, width)

    def _paint_tile(
        self,
        cells: list[list[tuple[str, Style]]],
        placed: _Placed,
        *,
        width: int,
        height: int,
    ) -> None:
        x0 = max(0, min(width, int(round(placed.x))))
        y0 = max(0, min(height, int(round(placed.y))))
        x1 = max(x0, min(width, int(round(placed.x + placed.width))))
        y1 = max(y0, min(height, int(round(placed.y + placed.height))))
        if x1 <= x0 or y1 <= y0:
            return
        item = placed.item
        selected = item.path is not None and item.path == self.selected_path
        background = brighter(item.color, 0.24) if selected else item.color
        background_style = Style(bgcolor=background)
        for row in range(y0, y1):
            for column in range(x0, x1):
                cells[row][column] = (" ", background_style)

        fg = contrast_text(background)
        label_start = x0 + (1 if x1 - x0 >= 14 else 0)
        available = x1 - label_start - 1
        if available >= 1 and y1 - y0 >= 1:
            if selected:
                marker_style = Style(bgcolor=background, color=ACCENT, bold=True)
                cells[y0][label_start] = ("▸", marker_style)
                if available >= 2:
                    cells[y0][label_start + 1] = (" ", marker_style)
                label_start += 2
                available -= 2
            if item.file is not None:
                label = self._tile_label(item.file, available)
            else:
                label = shorten_middle(clean_text(item.label), available)
            label_style = Style(bgcolor=background, color=fg, bold=True)
            for offset, character in enumerate(label[:available]):
                cells[y0][label_start + offset] = (character, label_style)

            if y1 - y0 >= 3 and x1 - x0 >= 9:
                if item.file is not None:
                    detail = self._best_detail(item.file, x1 - x0 - 2)
                else:
                    detail = shorten_end(item.note, x1 - x0 - 2)
                if detail:
                    detail_start = x0 + (1 if x1 - x0 >= 14 else 0)
                    detail_room = x1 - detail_start - 1
                    detail_style = Style(
                        bgcolor=background, color=mix(fg, background, 0.24)
                    )
                    if detail_room > 0:
                        for offset, character in enumerate(
                            shorten_end(detail, detail_room)
                        ):
                            cells[y0 + 1][detail_start + offset] = (
                                character,
                                detail_style,
                            )

        # A one-cell darker seam keeps adjacent tiles legible.  A selected
        # tile gets a lime bottom/right edge so it is easy to find in the map.
        seam_color = ACCENT if selected else mix(background, BACKGROUND, 0.58)
        seam = Style(bgcolor=seam_color)
        if y1 - y0 >= 2:
            for column in range(x0, x1):
                cells[y1 - 1][column] = (" ", seam)
        if x1 - x0 >= 4:
            for row in range(y0, y1 - 1):
                cells[row][x1 - 1] = (" ", seam)

    def _detail_label(self, file: FileMetric, *, compact: bool) -> str:
        if self.mode == "churn":
            if compact:
                return f"{file.commits}× · {human_count(file.churn)}Δ"
            return f"{file.commits} touches · {human_count(file.churn)} changed"
        if self.mode == "age":
            age = human_age(file.last_commit, self.now, long=not compact)
            return f"idle {age}" if file.last_commit is not None else "no history"
        if self.mode == "complexity":
            return (
                f"CC {file.max_complexity} · {file.sloc}L"
                if compact
                else f"CC {file.max_complexity} · {file.sloc} source lines"
            )
        return (
            f"risk {file.risk:.0f} · {file.commits}×"
            if compact
            else f"risk {file.risk:.0f} · {file.commits} touches"
        )

    def _best_detail(self, file: FileMetric, width: int) -> str:
        """Pick the richest detail line that still fits the tile."""
        if width <= 0:
            return ""
        if self.mode == "churn":
            candidates = [
                self._detail_label(file, compact=False),
                self._detail_label(file, compact=True),
                f"{file.commits}×" if file.commits else "",
            ]
        elif self.mode == "age":
            candidates = [
                self._detail_label(file, compact=False),
                self._detail_label(file, compact=True),
                human_age(file.last_commit, self.now) if file.last_commit else "new",
            ]
        elif self.mode == "complexity":
            candidates = [
                self._detail_label(file, compact=False),
                self._detail_label(file, compact=True),
                f"CC {file.max_complexity}",
                f"CC{file.max_complexity}",
            ]
        else:
            candidates = [
                self._detail_label(file, compact=False),
                self._detail_label(file, compact=True),
                f"risk {file.risk:.0f}",
                f"r{file.risk:.0f}",
            ]
        for candidate in candidates:
            if candidate and len(candidate) <= width:
                return candidate
        return ""

    def _legend(self, width: int) -> Text:
        labels = {
            "risk": ("low", "watch", "high", "critical"),
            "churn": ("quiet", "warm", "hot", "molten"),
            "age": ("fresh", "aging", "old", "fossil"),
            "complexity": ("simple", "dense", "tangled", "gnarly"),
        }[self.mode]
        stops = (0.04, 0.38, 0.7, 0.98)
        legend = Text(no_wrap=True, overflow="crop")
        legend.append("  ")
        for index, (label, stop) in enumerate(zip(labels, stops)):
            color = map_color(self.mode, stop)
            legend.append("██", style=color)
            legend.append(f" {label}", style=DIM)
            if index < len(labels) - 1:
                legend.append("  ")
        legend.append("     ")
        if width >= 96:
            legend.append(f"{MODE_HELP[self.mode]}", style=DIM)
        if width >= 112:
            legend.append("  ·  area ∝ LOC  ·  [c] recolor", style=DIM)
        elif width >= 60:
            legend.append("  ·  [c] recolor", style=DIM)
        return legend

    def render(self) -> Text:
        width, height = self.content_size
        if width <= 0 or height <= 0:
            return Text("")
        if not self.files:
            return Text("  no files in view — clear the filter or rescan", style=MUTED)
        legend_rows = 1 if height >= 3 else 0
        map_height = height - legend_rows
        if map_height <= 0:
            return Text("")
        items = self._items()
        placed = _strip_layout(items, 0.0, 0.0, float(width), float(map_height))
        base_style = Style(bgcolor="#0a120d")
        cells: list[list[tuple[str, Style]]] = [
            [(" ", base_style) for _ in range(width)] for _ in range(map_height)
        ]
        self._hitboxes = []
        for tile in placed:
            self._paint_tile(cells, tile, width=width, height=map_height)
            if tile.item.path is not None:
                x0 = max(0, min(width, int(round(tile.x))))
                y0 = max(0, min(map_height, int(round(tile.y))))
                x1 = max(x0, min(width, int(round(tile.x + tile.width))))
                y1 = max(y0, min(map_height, int(round(tile.y + tile.height))))
                self._hitboxes.append(
                    (x0, y0 + legend_rows, max(1, x1 - x0), max(1, y1 - y0), tile.item.path)
                )

        result = Text()
        if legend_rows:
            result.append_text(self._legend(width))
            result.append("\n")
        for row_index, row in enumerate(cells):
            active_style: Style | None = None
            run = ""
            for character, style in row:
                if style != active_style:
                    if run:
                        result.append(run, style=active_style)
                    run = character
                    active_style = style
                else:
                    run += character
            if run:
                result.append(run, style=active_style)
            if row_index < len(cells) - 1:
                result.append("\n")
        return result

    def on_click(self, event) -> None:
        # Textual reports mouse coordinates relative to the widget's content.
        for x, y, width, height, path in self._hitboxes:
            if path and x <= event.x < x + width and y <= event.y < y + height:
                self.post_message(self.TileClicked(path))
                event.stop()
                return
