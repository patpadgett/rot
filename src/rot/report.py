"""Static exports of a scan: a Rich report and machine-readable JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .format import (
    bar,
    clean_text,
    duration_ms,
    human_age,
    human_count,
    shorten_middle,
    shorten_path,
)
from .models import FileMetric, Snapshot
from .theme import (
    ACCENT,
    BORDER,
    DIM,
    GRID_LINE,
    MUTED,
    ORANGE,
    RED,
    TEAL,
    TEXT,
    YELLOW,
    grade_color,
    severity_color,
)


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def snapshot_payload(snapshot: Snapshot, *, demo: bool = False) -> dict[str, Any]:
    """Serialize the full scan for scripts and CI dashboards."""
    summary = snapshot.summary
    files = snapshot.sorted_files("risk")
    return {
        "schema": "rot.snapshot.v1",
        "version": __version__,
        "generated_at": _iso(snapshot.now),
        "demo": demo,
        "summary": {
            "root": summary.root,
            "name": summary.name,
            "branch": summary.branch,
            "head": summary.head,
            "files": summary.files,
            "loc": summary.loc,
            "sloc": summary.sloc,
            "commits": summary.commits,
            "authors": summary.authors,
            "history_files": summary.history_files,
            "recent_commits": summary.recent_commits,
            "recent_lines": summary.recent_lines,
            "first_commit": _iso(summary.first_commit),
            "last_commit": _iso(summary.last_commit),
            "dirty_files": summary.dirty_files,
            "untracked_files": summary.untracked_files,
            "risk_index": summary.risk_index,
            "risk_grade": summary.risk_grade,
            "health": summary.health,
            "critical": summary.critical,
            "high": summary.high,
            "medium": summary.medium,
            "low": summary.low,
            "stale_files": summary.stale_files,
            "stale_pct": _round(summary.stale_pct),
            "bus_factor": summary.bus_factor,
            "bus_share": _round(summary.bus_share, 4),
            "coverage_files": summary.coverage_files,
            "coverage_mode": summary.coverage_mode,
            "history_limit_reached": summary.history_limit_reached,
            "max_commits": summary.max_commits,
            "scan_ms": _round(summary.scan_ms),
            "warnings": list(summary.warnings),
        },
        "files": [_file_payload(file, snapshot) for file in files],
    }


def _file_payload(file: FileMetric, snapshot: Snapshot) -> dict[str, Any]:
    primary = file.primary_author
    return {
        "path": file.path,
        "language": file.language,
        "is_test": file.is_test,
        "risk": file.risk,
        "grade": file.grade(),
        "loc": file.loc,
        "sloc": file.sloc,
        "size": file.size,
        "complexity": {
            "max": file.max_complexity,
            "total": file.total_complexity,
            "depth": file.max_depth,
            "functions": file.functions,
            "classes": file.classes,
            "hot_function": file.hot_function or None,
            "score": _round(file.complexity_score),
            "parse_error": file.parse_error,
        },
        "history": {
            "commits": file.commits,
            "insertions": file.insertions,
            "deletions": file.deletions,
            "churn": file.churn,
            "recent_commits": file.recent_commits,
            "recent_lines": file.recent_lines,
            "first_commit": _iso(file.first_commit),
            "last_commit": _iso(file.last_commit),
            "age_days": _round(file.age_days(snapshot.now)),
            "last_author": file.last_author or None,
            "untracked": file.untracked,
            "dirty": file.dirty,
            "primary_author": primary.name if primary else None,
            "primary_share": _round(primary.share, 4) if primary else None,
            "authors": [
                {
                    "name": author.name,
                    "email": author.email,
                    "commits": author.commits,
                    "share": _round(author.share, 4),
                }
                for author in file.authors
            ],
            "activity": list(file.activity),
            "scores": {
                "churn": _round(file.churn_score),
                "ownership": _round(file.ownership_score),
            },
        },
        "tests": {
            "coverage": _round(file.coverage, 4),
            "coverage_source": file.coverage_source or None,
            "test_hits": file.test_hits,
            "test_files": list(file.test_files),
            "score": _round(file.test_score),
        },
        "staleness_score": _round(file.staleness_score),
        "factors": [
            {
                "key": factor.key,
                "label": factor.label,
                "detail": factor.detail,
                "severity": _round(factor.severity, 3),
            }
            for factor in sorted(
                file.factors, key=lambda item: item.severity, reverse=True
            )
        ],
    }


def export_json(snapshot: Snapshot, *, demo: bool = False) -> str:
    return json.dumps(snapshot_payload(snapshot, demo=demo), indent=2) + "\n"


def _banner(snapshot: Snapshot, *, demo: bool) -> Panel:
    summary = snapshot.summary
    title = Text()
    title.append(" rot ", style=f"bold #07100b on {ACCENT}")
    title.append(f" v{__version__} ", style=f"bold {TEXT}")
    title.append(" codebase entropy & health inspector", style=MUTED)
    if demo:
        title.append("  ·  demo fixture", style=f"bold {YELLOW}")

    repo = Text()
    repo.append("● ", style=ACCENT)
    repo.append(clean_text(summary.name), style=f"bold {TEXT}")
    repo.append("  ")
    repo.append(f" {clean_text(summary.branch)} ", style=f"bold #07100b on {ACCENT}")
    repo.append(f"  HEAD {summary.head}", style=MUTED)
    repo.append("  ·  ", style=DIM)
    repo.append(shorten_middle(clean_text(summary.root), 58), style=DIM)

    return Panel(
        Group(title, repo),
        border_style=BORDER,
        padding=(0, 1),
        expand=True,
    )


def _index_panel(snapshot: Snapshot) -> Panel:
    summary = snapshot.summary
    grade = summary.risk_grade
    color = grade_color(grade)
    text = Text()
    text.append(f"{summary.risk_index:.0f}", style=f"bold {color}")
    text.append(" / 100", style=DIM)
    text.append(f"  {grade.upper()}", style=f"bold {color}")
    text.append("\n")
    text.append(bar(summary.risk_index / 100, 20), style=color)
    text.append("\n")
    text.append(f"health {summary.health:.0f}/100", style=MUTED)
    return Panel(
        text,
        title="[bold]ROT INDEX[/bold]",
        title_align="left",
        border_style=color,
        padding=(0, 1),
    )


def _fact_panel(snapshot: Snapshot) -> Panel:
    summary = snapshot.summary
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", no_wrap=True)
    grid.add_column(no_wrap=True)

    def add(label: str, value: Text) -> None:
        grid.add_row(Text(label, style=MUTED), value)

    add(
        "hotspots",
        Text(
            f"{summary.critical + summary.high}",
            style=f"bold {RED if summary.critical else ORANGE if summary.high else TEAL}",
        ).append_text(
            Text(
                f"  ({summary.critical} critical / {summary.high} high)",
                style=DIM,
            )
        ),
    )
    bus_color = RED if summary.bus_factor <= 1 else ORANGE if summary.bus_factor <= 2 else YELLOW
    add(
        "bus factor",
        Text(f"{summary.bus_factor}", style=f"bold {bus_color}").append_text(
            Text(f"  covers {summary.bus_share:.0%} of commits", style=DIM)
        ),
    )
    stale_color = RED if summary.stale_pct >= 25 else ORANGE if summary.stale_pct >= 12 else TEAL
    add(
        "code rot",
        Text(f"{summary.stale_pct:.0f}%", style=f"bold {stale_color}").append_text(
            Text(f"  {summary.stale_files} files > 1 year", style=DIM)
        ),
    )
    add(
        "90d churn",
        Text(human_count(summary.recent_commits), style=f"bold {TEAL}").append_text(
            Text(f"  commits · {human_count(summary.recent_lines)} lines", style=DIM)
        ),
    )
    return Panel(
        grid,
        title="[bold]SIGNALS[/bold]",
        title_align="left",
        border_style=BORDER,
        padding=(0, 1),
    )


def _repo_panel(snapshot: Snapshot) -> Panel:
    summary = snapshot.summary
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", no_wrap=True)
    grid.add_column(no_wrap=True)

    def add(label: str, value: str, style: str = TEXT) -> None:
        grid.add_row(Text(label, style=MUTED), Text(value, style=style))

    add("source", f"{human_count(summary.files)} files · {human_count(summary.sloc)} sloc")
    add("history", f"{human_count(summary.commits)} commits · {summary.authors} authors")
    coverage = {
        "report": f"report · {summary.coverage_files} files",
        "linked": "test-link heuristic",
        "none": "no test signal",
    }.get(summary.coverage_mode, summary.coverage_mode)
    add("tests", coverage, TEAL if summary.coverage_mode == "report" else YELLOW)
    add("scanned", f"{duration_ms(summary.scan_ms / 1_000)} · offline")
    return Panel(
        grid,
        title="[bold]REPOSITORY[/bold]",
        title_align="left",
        border_style=BORDER,
        padding=(0, 1),
    )


_GRADE_SHORT = {
    "critical": "CRIT",
    "high": "HIGH",
    "medium": "MED",
    "low": "LOW",
    "calm": "CALM",
}


def _risk_table(
    files: list[FileMetric], now: float, top: int, *, compact: bool
) -> Table:
    table = Table(
        box=None,
        expand=True,
        padding=(0, 1),
        show_edge=False,
        header_style=f"bold {MUTED}",
    )
    table.add_column("RISK", justify="right", no_wrap=True, width=8)
    if not compact:
        table.add_column("GRADE", no_wrap=True, width=6)
    table.add_column("FILE", no_wrap=True, overflow="ellipsis", ratio=1, min_width=18)
    table.add_column("CC", justify="right", no_wrap=True, width=3)
    table.add_column("TOUCH", justify="right", no_wrap=True, width=5)
    table.add_column("LAST", justify="right", no_wrap=True, width=5)
    table.add_column("OWN", justify="right", no_wrap=True, width=4)
    table.add_column("TEST", justify="right", no_wrap=True, width=4)
    if not compact:
        table.add_column("TOP SIGNAL", no_wrap=True, overflow="ellipsis", width=18)

    for file in files[:top]:
        grade = file.grade()
        color = grade_color(grade)
        owner = file.primary_author
        if owner:
            own = Text(
                f"{owner.share:.0%}",
                style=RED
                if owner.share >= 0.65
                else ORANGE
                if owner.share >= 0.4
                else TEXT,
            )
        else:
            own = Text("—", style=DIM)
        if file.coverage is not None:
            test = Text(
                f"{file.coverage:.0%}",
                style=TEAL
                if file.coverage >= 0.7
                else YELLOW
                if file.coverage >= 0.4
                else RED,
            )
        elif file.test_hits:
            test = Text(f"~{min(99, int(file.test_score))}%", style=YELLOW)
        else:
            test = Text("—", style=RED if not file.is_test else DIM)
        row: list[Text] = [
            Text(f"{file.risk:>4.1f}", style=f"bold {color}"),
        ]
        if not compact:
            row.append(Text(_GRADE_SHORT.get(grade, grade.upper()), style=color))
        row.extend(
            [
                Text(shorten_path(clean_text(file.path), 58), style=TEXT),
                Text(
                    str(file.max_complexity),
                    style=ORANGE if file.max_complexity >= 15 else TEXT,
                ),
                Text(
                    str(file.commits) if file.commits else "—",
                    style=TEXT if file.commits else DIM,
                ),
                Text(human_age(file.last_commit, now), style=MUTED),
                own,
                test,
            ]
        )
        if not compact:
            factors = file.factors_for_display(1)
            if factors:
                factor = factors[0]
                row.append(
                    Text(
                        clean_text(factor.label),
                        style=f"bold {severity_color(factor.severity)}",
                    )
                )
            else:
                row.append(Text("stable", style=TEAL))
        table.add_row(*row)
    return table


def print_report(
    snapshot: Snapshot,
    console: Console | None = None,
    *,
    demo: bool = False,
    top: int = 20,
    filter_text: str = "",
) -> None:
    """Print a static dashboard suitable for CI logs or a README."""
    console = console or Console()
    summary = snapshot.summary
    files = snapshot.sorted_files("risk")
    if filter_text:
        query = filter_text.lower()
        files = [file for file in files if query in file.path.lower()]

    console.print(_banner(snapshot, demo=demo))
    console.print()

    width = console.width
    if width >= 116:
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=2)
        grid.add_column(ratio=3)
        grid.add_column(ratio=3)
        grid.add_row(
            _index_panel(snapshot), _fact_panel(snapshot), _repo_panel(snapshot)
        )
        console.print(grid)
    elif width >= 76:
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=2)
        grid.add_column(ratio=3)
        grid.add_row(_index_panel(snapshot), _fact_panel(snapshot))
        console.print(grid)
        console.print(_repo_panel(snapshot))
    else:
        console.print(_index_panel(snapshot))
        console.print(_fact_panel(snapshot))
        console.print(_repo_panel(snapshot))
    console.print()

    heading = Text()
    heading.append(" TOP ROT RISKS", style=f"bold {ORANGE}")
    heading.append(f"  {len(files)} file{'s' if len(files) != 1 else ''} in view", style=DIM)
    if filter_text:
        heading.append(f" · filter “{clean_text(filter_text)}”", style=DIM)
    console.print(heading)
    console.print(Text("─" * max(40, console.width - 1), style=GRID_LINE))
    if files:
        console.print(
            _risk_table(files, snapshot.now, top, compact=console.width < 112)
        )
        if len(files) > top:
            console.print(Text(f"  … {len(files) - top} more files (use --top to widen this table)", style=DIM))
    else:
        console.print(Text("  no supported source files matched", style=YELLOW))
    console.print()

    if summary.warnings:
        console.print(
            Panel(
                "\n".join(f"  · {warning}" for warning in summary.warnings),
                title="[bold]NOTES[/bold]",
                title_align="left",
                border_style=YELLOW,
                padding=(0, 1),
            )
        )
        console.print()

    footer = Text()
    footer.append("  rot", style=f"bold {ACCENT}")
    footer.append(" dashboard  ·  ", style=DIM)
    footer.append("rot --json", style=f"bold {ACCENT}")
    footer.append(" ci  ·  ", style=DIM)
    footer.append("rot --help", style=f"bold {ACCENT}")
    footer.append(" options", style=DIM)
    console.print(footer)
