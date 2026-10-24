"""The interactive Textual dashboard."""

from __future__ import annotations

import time
from pathlib import Path

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Footer, Input, Static

from .demo import demo_snapshot
from .format import (
    clean_text,
    human_age,
    human_count,
    shorten_path,
    shorten_middle,
)
from .models import FileMetric, Snapshot
from .screens import HelpScreen, InspectScreen
from .score import compute_risk_index
from .scan import scan_repository
from .theme import (
    ACCENT,
    DIM,
    MUTED,
    ORANGE,
    PURPLE,
    RED,
    TEAL,
    TEXT,
    YELLOW,
    grade_color,
    language_color,
)
from .widgets import BrandBar, MetricCard, Treemap

SORT_MODES = ("risk", "churn", "complexity", "age", "name")
SORT_LABELS = {
    "risk": "risk",
    "churn": "churn",
    "complexity": "complexity",
    "age": "age",
    "name": "path",
}
MAX_TABLE_ROWS = 1_500


class _FileTable(DataTable):
    """A DataTable that tells the app when its content box changes size.

    The app's own ``on_resize`` never runs because Textual's internal App
    handler consumes window resize events.  Widgets do receive resizes, so the
    table forwards its new geometry and the dashboard can refit its columns
    after a live terminal resize.
    """

    class Resized(Message):
        pass

    def on_resize(self, event: events.Resize) -> None:
        self.post_message(self.Resized())


class RotApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "rot"
    SUB_TITLE = "codebase entropy inspector"

    # The dashboard is dense; these breakpoints keep it usable from a classic
    # 80x24 terminal up to a full-screen split view.
    HORIZONTAL_BREAKPOINTS = [
        (0, "-narrow"),
        (96, "-medium"),
        (124, "-wide"),
    ]
    VERTICAL_BREAKPOINTS = [
        (0, "-tiny"),
        (28, "-short"),
        (34, "-regular"),
        (44, "-tall"),
    ]

    BINDINGS = [
        Binding("enter", "inspect", "Inspect", show=True),
        Binding("f,slash", "focus_filter", "Filter", show=True),
        Binding("s", "cycle_sort", "Sort", show=True),
        Binding("c", "cycle_map", "Map lens", show=True),
        Binding("g", "first_file", "First", show=False),
        Binding("G", "last_file", "Last", show=False),
        Binding("r", "rescan", "Rescan", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "escape", "Clear / close", show=False),
    ]

    def __init__(
        self,
        snapshot: Snapshot,
        *,
        repo_path: str | Path | None = None,
        demo: bool = False,
        max_commits: int = 5_000,
        max_files: int = 6_000,
        initial_filter: str = "",
    ) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.repo_path = Path(repo_path or snapshot.summary.root)
        self.demo = demo
        self.max_commits = max_commits
        self.max_files = max_files
        self.sort_mode = "risk"
        self.map_mode = "risk"
        self.filter_text = initial_filter.strip()
        self.selected_path: str | None = None
        self._visible_files: list[FileMetric] = []
        self._table_files: list[FileMetric] = []
        self._row_index: dict[str, int] = {}
        self._filter_visible = bool(self.filter_text)
        self._scanning = False
        self._last_inspect = 0.0
        self._last_file_width = -1

    # -- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield BrandBar(id="brand")
        with Horizontal(id="metrics"):
            yield MetricCard("ROT INDEX", id="metric-risk")
            yield MetricCard("HOTSPOTS", id="metric-hotspots")
            yield MetricCard("BUS FACTOR", id="metric-bus")
            yield MetricCard("CODE ROT", id="metric-stale")
            yield MetricCard("90D CHURN", id="metric-churn")
        yield Treemap(id="map")
        with Horizontal(id="body"):
            yield _FileTable(
                id="files",
                cursor_type="row",
                cell_padding=0,
                zebra_stripes=False,
                cursor_foreground_priority="renderable",
            )
            with VerticalScroll(id="dossier"):
                yield Static("", id="dossier-body")
        yield Input(
            value=self.filter_text,
            placeholder="filter paths…  type to narrow, enter to apply, esc to clear",
            id="filter",
            compact=True,
        )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self._brand = self.query_one("#brand", BrandBar)
        self._map = self.query_one("#map", Treemap)
        self._metrics = {
            "risk": self.query_one("#metric-risk", MetricCard),
            "hotspots": self.query_one("#metric-hotspots", MetricCard),
            "bus": self.query_one("#metric-bus", MetricCard),
            "stale": self.query_one("#metric-stale", MetricCard),
            "churn": self.query_one("#metric-churn", MetricCard),
        }
        self._table = self.query_one("#files", DataTable)
        self._dossier_scroll = self.query_one("#dossier", VerticalScroll)
        self._dossier_body = self.query_one("#dossier-body", Static)
        self._filter_input = self.query_one("#filter", Input)
        self._table.border_title = " HIGH-RISK ZONES "
        self._dossier_scroll.border_title = " FILE DOSSIER "
        self._filter_input.value = self.filter_text
        if self._filter_visible:
            self._filter_input.add_class("filter-visible")
        self._configure_table()
        self._apply_snapshot(self.snapshot, first=True)
        self._table.focus()
        self.call_after_refresh(self._fit_table_columns)
        warnings = self.snapshot.summary.warnings
        if warnings and not self.demo:
            for warning in warnings[:2]:
                self.notify(warning, severity="warning", timeout=10, markup=False)

    def on_unmount(self) -> None:
        pass

    def _configure_table(self) -> None:
        table = self._table
        table.add_column(Text("RISK", style=f"bold {MUTED}"), width=10, key="risk")
        table.add_column(Text("FILE", style=f"bold {MUTED}"), width=44, key="file")
        table.add_column(
            Text("TOUCH", justify="right", style=f"bold {MUTED}"),
            width=6,
            key="churn",
        )
        table.add_column(
            Text("CC", justify="right", style=f"bold {MUTED}"),
            width=5,
            key="complexity",
        )
        table.add_column(
            Text("AGE", justify="right", style=f"bold {MUTED}"),
            width=6,
            key="age",
        )
        table.add_column(
            Text("OWN", justify="right", style=f"bold {MUTED}"),
            width=5,
            key="owner",
        )
        table.add_column(
            Text(" TEST", justify="right", style=f"bold {MUTED}"),
            width=5,
            key="test",
        )
        table.border_title = " HIGH-RISK ZONES "

    def _fit_table_columns(self) -> None:
        width = self._table.content_size.width
        if width <= 0:
            return
        # Keep every column visible down to a ~50-cell table: the dashboard is
        # meant to be readable in a split pane, not horizontally scrolled. Two
        # cells reserve room for the vertical scrollbar and its corner.
        fixed = 10 + 5 + 4 + 5 + 5 + 5
        file_width = max(18, width - fixed - 2)
        if file_width == self._last_file_width:
            return
        self._last_file_width = file_width
        for key, column_width in (
            ("risk", 10),
            ("file", file_width),
            ("churn", 5),
            ("complexity", 4),
            ("age", 5),
            ("owner", 5),
            ("test", 5),
        ):
            if key in self._table.columns:
                self._table.columns[key].width = column_width
        self._table.refresh()
        # Cell text is rendered with the *current* file width, so rebuild the
        # rows after a column resize instead of leaving stale truncated paths.
        if self._table.row_count:
            self.call_after_refresh(self._render_table)

    @on(_FileTable.Resized)
    def _file_table_resized(self) -> None:
        self.call_after_refresh(self._fit_table_columns)

    # -- data flow -------------------------------------------------------

    def _apply_snapshot(self, snapshot: Snapshot, *, first: bool = False) -> None:
        self.snapshot = snapshot
        self._brand.set_snapshot(snapshot)
        self._update_metrics()
        if self.selected_path is None or not any(
            file.path == self.selected_path for file in snapshot.files
        ):
            ordered = snapshot.sorted_files(self.sort_mode)
            self.selected_path = ordered[0].path if ordered else None
        self._refresh_view()
        if not first:
            self.notify(
                f"rescan complete · {snapshot.summary.scan_ms:.0f} ms",
                timeout=2,
                markup=False,
            )

    def _update_metrics(self) -> None:
        summary = self.snapshot.summary
        source = [file for file in self.snapshot.files if not file.is_test]
        source_total = max(1, len(source))
        risk = summary.risk_index
        self._metrics["risk"].set_metric(
            f"{risk:.0f}",
            badge=summary.risk_grade.upper(),
            subtitle=f"health {summary.health:.0f}/100",
            ratio=risk / 100,
            color=grade_color(summary.risk_grade),
        )
        hotspots = summary.critical + summary.high
        hotspots_color = RED if summary.critical else ORANGE if summary.high else TEAL
        self._metrics["hotspots"].set_metric(
            f"{hotspots}",
            badge="FILES",
            subtitle=f"{summary.critical} crit · {summary.high} high",
            ratio=hotspots / source_total,
            color=hotspots_color,
        )
        bus_color = (
            RED if summary.bus_factor <= 1 else ORANGE if summary.bus_factor == 2 else YELLOW if summary.bus_factor <= 4 else TEAL
        )
        self._metrics["bus"].set_metric(
            f"{summary.bus_factor}",
            badge="PEOPLE",
            subtitle=f"cover {summary.bus_share:.0%} of commits",
            ratio=summary.bus_share,
            color=bus_color,
        )
        stale_color = (
            RED if summary.stale_pct >= 25 else ORANGE if summary.stale_pct >= 12 else YELLOW if summary.stale_pct >= 5 else TEAL
        )
        self._metrics["stale"].set_metric(
            f"{summary.stale_pct:.0f}%",
            subtitle=f"{summary.stale_files} files > 1 year",
            ratio=summary.stale_pct / 100,
            color=stale_color,
        )
        self._metrics["churn"].set_metric(
            human_count(summary.recent_commits),
            subtitle=f"{human_count(summary.recent_lines)} lines · {human_count(summary.commits)} total",
            ratio=min(1.0, summary.recent_commits / 100),
            color=TEAL,
        )

    def _filtered_sorted(self) -> list[FileMetric]:
        query = self.filter_text.lower()
        files = self.snapshot.sorted_files(self.sort_mode)
        if query:
            files = [file for file in files if query in file.path.lower()]
        return files

    def _refresh_view(self) -> None:
        self._visible_files = self._filtered_sorted()
        available = self._visible_files
        self._table_files = available[:MAX_TABLE_ROWS]
        if self.selected_path is None or not any(
            file.path == self.selected_path for file in available
        ):
            self.selected_path = available[0].path if available else None
        self._render_table()
        self._render_dossier()
        self._map.set_mode(self.map_mode)
        self._map.set_data(available, selected_path=self.selected_path, now=self.snapshot.now)
        self._update_subtitles()

    def _update_subtitles(self) -> None:
        total = len(self._visible_files)
        shown = len(self._table_files)
        parts = [f"{total} file{'s' if total != 1 else ''}"]
        if shown < total:
            parts.append(f"{shown} shown")
        parts.append(f"sort {SORT_LABELS[self.sort_mode]}")
        if self.filter_text:
            parts.append(f"filter “{clean_text(shorten_middle(self.filter_text, 24))}”")
        parts.append("enter inspects")
        self._table.border_subtitle = " · ".join(parts)
        self._dossier_scroll.border_subtitle = (
            f" {shorten_middle(clean_text(self.selected_path), 40)} " if self.selected_path else " no selection "
        )

    def _render_table(self) -> None:
        table = self._table
        # Keep column geometry in sync before rendering, since cell text is
        # shortened against the current FILE width.
        self._fit_table_columns()
        selected = self.selected_path
        table.clear(columns=False)
        self._row_index = {}
        for index, file in enumerate(self._table_files):
            self._row_index[file.path] = index
            table.add_row(
                self._risk_cell(file),
                self._file_cell(file),
                self._touch_cell(file),
                self._complexity_cell(file),
                self._age_cell(file),
                self._owner_cell(file),
                self._test_cell(file),
                key=file.path,
            )
        if not self._table_files:
            self._map.set_selected(None)
            return
        row = self._row_index.get(selected or "", 0)
        if selected is None:
            selected = self._table_files[0].path
            self.selected_path = selected
        table.move_cursor(row=row, animate=False)
        self._map.set_selected(self.selected_path)

    def _risk_cell(self, file: FileMetric) -> Text:
        color = grade_color(file.grade())
        blocks = "█" * max(1, int(round(file.risk / 100 * 5)))
        blocks += "░" * (5 - len(blocks))
        text = Text(no_wrap=True)
        text.append(" ")
        text.append(blocks, style=color)
        text.append(f" {file.risk:>3.0f}", style=f"bold {color}")
        return text

    def _file_cell(self, file: FileMetric) -> Text:
        from .analyze import language_label

        width = self._last_file_width if self._last_file_width > 0 else 44
        label = shorten_middle(language_label(file.language), 4)
        suffix = ""
        if file.is_test:
            suffix += " ·t"
        if file.dirty or file.untracked:
            suffix += "*"
        path_width = max(8, width - 5 - len(suffix) - 1)
        path = shorten_path(file.path, path_width)
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f" {label:<4}", style=f"bold {language_color(file.language)}")
        head, separator, name = path.rpartition("/")
        if separator:
            text.append(head + "/", style=DIM)
        text.append(name or path, style=f"bold {TEXT}")
        if suffix:
            text.append(suffix, style=DIM)
        text.append(" ")
        return text

    def _touch_cell(self, file: FileMetric) -> Text:
        if file.commits:
            color = RED if file.churn_score >= 72 else ORANGE if file.churn_score >= 50 else TEXT
            return Text(f"{file.commits} ", style=color)
        return Text("— ", style=DIM)

    def _complexity_cell(self, file: FileMetric) -> Text:
        color = RED if file.complexity_score >= 72 else ORANGE if file.complexity_score >= 50 else TEXT
        return Text(f"{file.max_complexity} ", style=color)

    def _age_cell(self, file: FileMetric) -> Text:
        if file.last_commit is None:
            return Text("— ", style=DIM)
        color = RED if file.staleness_score >= 60 else ORANGE if file.staleness_score >= 30 else MUTED
        return Text(f"{human_age(file.last_commit, self.snapshot.now)} ", style=color)

    def _owner_cell(self, file: FileMetric) -> Text:
        author = file.primary_author
        if author is None:
            return Text("— ", style=DIM)
        color = RED if author.share >= 0.65 else ORANGE if author.share >= 0.4 else TEXT
        return Text(f"{author.share:.0%} ", style=color)

    def _test_cell(self, file: FileMetric) -> Text:
        if file.coverage is not None:
            color = TEAL if file.coverage >= 0.7 else ORANGE if file.coverage >= 0.4 else RED
            return Text(f"{file.coverage:.0%} ", style=color)
        if file.test_hits:
            return Text(f"~{min(99, int(file.test_score))}% ", style=ORANGE)
        if file.is_test:
            return Text("·t ", style=DIM)
        return Text("— ", style=RED)

    def _render_dossier(self) -> None:
        metric = self._selected_metric()
        if metric is None:
            text = Text()
            text.append("\n NO FILE IN VIEW\n\n", style=f"bold {MUTED}")
            if self.filter_text:
                text.append(" Nothing matches the current path filter.\n", style=DIM)
                text.append(" Press esc to clear it or r to rescan.\n", style=DIM)
            else:
                text.append(" The scanner found no supported source files.\n", style=DIM)
            self._dossier_body.update(text)
        else:
            from .render import dossier_text

            self._dossier_body.update(dossier_text(metric, self.snapshot.now))

    def _selected_metric(self) -> FileMetric | None:
        if self.selected_path is None:
            return None
        return next(
            (file for file in self._visible_files if file.path == self.selected_path),
            None,
        )

    # -- interaction -----------------------------------------------------

    @on(DataTable.RowHighlighted, "#files")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        path = event.row_key.value
        if not path:
            return
        self.selected_path = str(path)
        self._render_dossier()
        self._map.set_selected(self.selected_path)
        self._update_subtitles()

    @on(DataTable.RowSelected, "#files")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        path = event.row_key.value
        if path:
            self.selected_path = str(path)
            self._open_inspect()

    @on(Treemap.TileClicked)
    def _treemap_clicked(self, event: Treemap.TileClicked) -> None:
        if event.path not in self._row_index:
            # Clicked a tile that is not in the table window; still inspect it.
            self.selected_path = event.path
            self._render_dossier()
            self._map.set_selected(event.path)
            self._update_subtitles()
            return
        self.selected_path = event.path
        self._table.move_cursor(row=self._row_index[event.path], animate=False)
        self._table.focus()

    def action_inspect(self) -> None:
        if isinstance(self.screen, InspectScreen):
            return
        if self._filter_visible and self._filter_input.has_focus:
            return
        self._open_inspect()

    def _open_inspect(self) -> None:
        now = time.monotonic()
        if now - self._last_inspect < 0.2:
            return
        self._last_inspect = now
        metric = self._selected_metric()
        if metric is None:
            self.notify("select a file first", severity="warning", timeout=2)
            return
        self.push_screen(InspectScreen(metric, self.snapshot.summary, self.snapshot.now))

    def action_focus_filter(self) -> None:
        self._show_filter(focus=True)

    def _show_filter(self, *, focus: bool) -> None:
        self._filter_visible = True
        self._filter_input.add_class("filter-visible")
        self._filter_input.value = self.filter_text
        if focus:
            self._filter_input.focus()
            self._filter_input.cursor_position = len(self._filter_input.value)
        self.call_after_refresh(self._fit_table_columns)

    def _hide_filter(self) -> None:
        self._filter_visible = False
        self._filter_input.remove_class("filter-visible")
        self.call_after_refresh(self._fit_table_columns)

    @on(Input.Changed, "#filter")
    def _filter_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if query == self.filter_text:
            return
        self.filter_text = query
        self._refresh_view()

    @on(Input.Submitted, "#filter")
    def _filter_submitted(self) -> None:
        self._hide_filter()
        self._table.focus()

    def action_escape(self) -> None:
        if self._filter_visible:
            if self.filter_text:
                self.filter_text = ""
                self._filter_input.value = ""
                self._refresh_view()
            self._hide_filter()
            self._table.focus()
            return
        if self.filter_text:
            self.filter_text = ""
            self._filter_input.value = ""
            self._refresh_view()
            self._table.focus()

    def action_cycle_sort(self) -> None:
        index = SORT_MODES.index(self.sort_mode)
        self.sort_mode = SORT_MODES[(index + 1) % len(SORT_MODES)]
        self._refresh_view()

    def action_cycle_map(self) -> None:
        modes = Treemap.MODES
        index = modes.index(self.map_mode)
        self.map_mode = modes[(index + 1) % len(modes)]
        self._map.set_mode(self.map_mode)
        self._map.set_data(
            self._visible_files,
            selected_path=self.selected_path,
            now=self.snapshot.now,
        )

    def action_first_file(self) -> None:
        if self._table.row_count:
            self._table.move_cursor(row=0, animate=False)

    def action_last_file(self) -> None:
        if self._table.row_count:
            self._table.move_cursor(row=self._table.row_count - 1, animate=False)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_rescan(self) -> None:
        if self._scanning:
            return
        if self.demo:
            self._scanning = True
            self._brand.set_scanning(True)
            snapshot = demo_snapshot()
            self._scanning = False
            self._brand.set_scanning(False)
            self._apply_snapshot(snapshot)
            return
        self._scanning = True
        self._brand.set_scanning(True)
        self.notify("rescanning working tree…", timeout=1.2, markup=False)
        self._rescan_worker()

    @work(thread=True, exclusive=True, group="rescan")
    def _rescan_worker(self) -> None:
        try:
            snapshot = scan_repository(
                self.repo_path,
                max_commits=self.max_commits,
                max_files=self.max_files,
            )
        except Exception as error:
            self.call_from_thread(self._rescan_failed, f"{type(error).__name__}: {error}")
            return
        self.call_from_thread(self._rescan_finished, snapshot)

    def _rescan_finished(self, snapshot: Snapshot) -> None:
        self._scanning = False
        self._brand.set_scanning(False)
        self._apply_snapshot(snapshot)

    def _rescan_failed(self, message: str) -> None:
        self._scanning = False
        self._brand.set_scanning(False)
        self.notify(message, title="scan failed", severity="error", timeout=8, markup=False)
