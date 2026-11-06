"""Rich text renderers for the dossier, inspection modal, and help."""

from __future__ import annotations

from rich.text import Text

from .analyze import language_label
from .format import (
    bar,
    clean_text,
    clean_text as safe,
    human_age,
    human_count,
    shorten_middle,
)
from .models import FileMetric, RepoSummary
from .theme import (
    ACCENT,
    DIM,
    GRID_LINE,
    MUTED,
    ORANGE,
    PURPLE,
    RED,
    TEAL,
    TEXT,
    YELLOW,
    grade_color,
    language_color,
    mix,
    severity_color,
)

_SPARK = "▁▂▃▄▅▆▇█"


def _divider() -> str:
    return "─" * 40


def _risk_color(file: FileMetric) -> str:
    return grade_color(file.grade())


def _spark_text(values: list[int], color: str = TEAL) -> Text:
    values = (list(values) + [0] * 12)[:12]
    peak = max(values) if values else 0
    text = Text()
    for index, value in enumerate(values):
        if value <= 0:
            text.append("·", style=DIM)
            continue
        height = 1 + int((value / peak) * (len(_SPARK) - 2)) if peak else 1
        height = min(len(_SPARK) - 1, height)
        shade = mix(color, "#dff8ec", 0.08 * index)
        text.append(_SPARK[height], style=shade)
    return text


def BACKGROUND_ON_LANG(color: str) -> str:
    # Small local helper: use the dark background as the tag's background so
    # the language tag reads at a fixed contrast against any ramp color.
    return "#07100b"


def _lang_tag(file: FileMetric) -> Text:
    tag = Text()
    color = language_color(file.language)
    tag.append(
        f" {language_label(file.language)} ",
        style=f"bold {BACKGROUND_ON_LANG(color)} on {color}",
    )
    return tag


def _status_tags(file: FileMetric) -> Text:
    tags = Text()
    if file.is_test:
        tags.append(" TEST ", style=f"bold {TEXT} on #314a3d")
    if file.untracked:
        tags.append(" UNTRACKED ", style=f"bold #1a0c0d on {YELLOW}")
    if file.dirty:
        tags.append(" DIRTY ", style=f"bold #1a0c0d on {ORANGE}")
    if file.parse_error:
        tags.append(" PARSE? ", style=f"bold #1a0c0d on {RED}")
    return tags


def _stat_line(
    text: Text,
    label: str,
    value: str,
    *,
    color: str = TEXT,
    note: str = "",
) -> None:
    text.append(f"  {label:<12}", style=f"bold {MUTED}")
    text.append(value, style=f"bold {color}")
    if note:
        text.append(f"  {note}", style=f"{DIM}")
    text.append("\n")


def _test_text(file: FileMetric) -> tuple[str, str, str]:
    if file.is_test:
        return "test file", "coverage penalties off", MUTED
    if file.coverage is not None:
        color = TEAL if file.coverage >= 0.7 else (YELLOW if file.coverage >= 0.4 else RED)
        return f"{file.coverage:.0%}", f"{file.coverage_source or 'report'}", color
    if file.test_hits:
        return (
            f"{file.test_hits} ref{'s' if file.test_hits != 1 else ''}",
            "link signal · heuristic",
            YELLOW,
        )
    return "none", "no test references", RED


def _factor_line(factor, text: Text) -> None:
    color = severity_color(factor.severity)
    text.append("  ▲ ", style=color)
    text.append(f"{safe(factor.label)}", style=f"bold {color}")
    text.append(f" · {safe(factor.detail)}\n", style=MUTED)


def dossier_text(file: FileMetric, now: float) -> Text:
    color = _risk_color(file)
    text = Text()
    text.append(" ")
    text.append_text(_lang_tag(file))
    text.append("  ")
    text.append(safe(file.path), style=f"bold {TEXT}")
    tags = _status_tags(file)
    if tags.plain:
        text.append(" ")
        text.append_text(tags)
    text.append("\n")

    risk_text = f"{file.risk:.0f}"
    text.append("  RISK ", style=f"bold {MUTED}")
    text.append(risk_text, style=f"bold {color}")
    text.append(" / 100   ", style=DIM)
    text.append(file.grade().upper(), style=f"bold {color}")
    text.append("\n  ")
    text.append(bar(file.risk / 100, 30), style=color)
    text.append("\n")
    text.append(f"  {_divider()}\n", style=GRID_LINE)

    complexity_detail = (
        f"CC {file.max_complexity} max / {file.total_complexity} total"
    )
    if file.hot_function:
        complexity_detail += f" · {safe(file.hot_function)}()"
    comp_color = (
        RED
        if file.complexity_score >= 72
        else ORANGE
        if file.complexity_score >= 50
        else YELLOW
        if file.complexity_score >= 35
        else TEAL
    )
    _stat_line(text, "COMPLEXITY", complexity_detail, color=comp_color)

    churn_color = (
        RED
        if file.churn_score >= 72
        else ORANGE
        if file.churn_score >= 50
        else TEAL
    )
    churn_detail = (
        f"{file.commits} touches · {human_count(file.churn)} Δ"
        if file.commits
        else "no history"
    )
    _stat_line(text, "CHURN", churn_detail, color=churn_color)

    age = human_age(file.last_commit, now, long=True)
    stale_color = RED if file.staleness_score >= 65 else ORANGE if file.staleness_score >= 35 else TEAL
    _stat_line(text, "LAST CHANGE", age, color=stale_color)

    if file.primary_author:
        owner = shorten_middle(clean_text(file.primary_author.name), 19)
        owner_text = f"{owner} · {file.primary_author.share:.0%}"
        owner_note = f"{file.author_count} author{'s' if file.author_count != 1 else ''}"
        owner_color = RED if file.ownership_score >= 65 else ORANGE if file.ownership_score >= 40 else TEAL
    else:
        owner_text = "no recorded author"
        owner_note = "untracked" if file.untracked else ""
        owner_color = MUTED
    _stat_line(text, "OWNERSHIP", owner_text, color=owner_color, note=owner_note)

    test_value, test_note, test_color = _test_text(file)
    _stat_line(text, "TESTS", test_value, color=test_color, note=test_note)

    pulse = _spark_text(file.activity, TEAL)
    text.append(f"  {'PULSE':<12}", style=f"bold {MUTED}")
    text.append_text(pulse)
    text.append("  12mo\n", style=DIM)

    text.append("\n  ROT SIGNALS\n", style=f"bold {ORANGE}")
    factors = file.factors_for_display(3)
    if factors:
        for factor in factors:
            _factor_line(factor, text)
    else:
        text.append("  ● no active rot signals\n", style=TEAL)
    if len(file.factors) > 3:
        text.append(
            f"  + {len(file.factors) - 3} more · enter for full dossier\n",
            style=DIM,
        )

    text.append(f"  {_divider()}\n", style=GRID_LINE)
    text.append("  BLAST RADIUS\n", style=f"bold {PURPLE}")
    if file.authors:
        for author in file.authors[:3]:
            name = shorten_middle(clean_text(author.name), 16)
            share_color = (
                RED if author.share >= 0.65 else ORANGE if author.share >= 0.4 else TEAL
            )
            text.append(f"  {name:<16}", style=TEXT)
            text.append(bar(author.share, 8), style=share_color)
            text.append(f" {author.share:>3.0%}", style=f"bold {share_color}")
            text.append(f"  {author.commits} touch{'es' if author.commits != 1 else ''}\n", style=DIM)
    else:
        text.append("  no commit history yet\n", style=DIM)
    text.append("\n")
    return text


def inspect_text(file: FileMetric, summary: RepoSummary, now: float) -> Text:
    color = _risk_color(file)
    text = Text()
    text.append(" FILE DOSSIER ", style=f"bold {BACKGROUND_ON_LANG(color)} on {color}")
    text.append("  ")
    text.append(safe(file.path), style=f"bold {TEXT}")
    tags = _status_tags(file)
    if tags.plain:
        text.append(" ")
        text.append_text(tags)
    text.append("\n")
    text.append(
        f" {summary.name} / {summary.branch}  ·  {language_label(file.language)}  ·  "
        f"{file.sloc:,} source lines / {file.loc:,} total\n",
        style=MUTED,
    )
    text.append("\n")

    text.append(" RISK ", style=f"bold {MUTED}")
    text.append(f"{file.risk:.1f}", style=f"bold {color}")
    text.append(f" / 100  {file.grade().upper()}\n", style=color)
    text.append(" ")
    text.append(bar(file.risk / 100, 52), style=color)
    text.append("\n")
    text.append(f" {_divider()}\n", style=GRID_LINE)

    text.append(" STRUCTURE\n", style=f"bold {ACCENT}")
    _stat_line(text, "Complexity", f"CC {file.max_complexity} max / {file.total_complexity} total", color=TEXT)
    if file.hot_function:
        _stat_line(text, "Hot function", f"{safe(file.hot_function)}()", color=ORANGE)
    _stat_line(text, "Nesting", f"{file.max_depth} levels", color=ORANGE if file.max_depth >= 5 else TEAL)
    _stat_line(text, "Definitions", f"{file.functions} functions · {file.classes} classes")
    _stat_line(text, "Size", f"{file.sloc:,} sloc · {file.loc:,} loc")

    text.append("\n HISTORY\n", style=f"bold {ACCENT}")
    _stat_line(text, "Touches", f"{file.commits} commits", color=TEXT, note=f"{file.recent_commits} in the last 90 days")
    _stat_line(text, "Churn", f"+{file.insertions:,} / -{file.deletions:,}", color=TEXT)
    _stat_line(text, "Last touch", human_age(file.last_commit, now, long=True), color=TEXT)
    _stat_line(text, "First seen", human_age(file.first_commit, now, long=True), color=TEXT)
    if file.last_author:
        _stat_line(text, "Last by", safe(file.last_author), color=TEXT)

    text.append("\n TEST SIGNAL\n", style=f"bold {ACCENT}")
    if file.coverage is not None:
        _stat_line(text, "Coverage", f"{file.coverage:.1%}", color=TEAL if file.coverage >= 0.6 else YELLOW, note=f"from {file.coverage_source}")
    else:
        _stat_line(text, "Coverage", "no report found", color=YELLOW)
        text.append("  Using conservative test-file references as a signal.\n", style=DIM)
    if file.test_files:
        text.append("  Linked tests:\n", style=MUTED)
        for test_name in file.test_files[:6]:
            text.append(f"    · {safe(test_name)}\n", style=DIM)
    elif file.test_hits:
        text.append(f"  {file.test_hits} test reference(s) linked.\n", style=MUTED)
    else:
        text.append("  No test file references this module.\n", style=MUTED)

    text.append("\n ROT SIGNALS\n", style=f"bold {ACCENT}")
    if file.factors:
        for factor in sorted(file.factors, key=lambda item: item.severity, reverse=True):
            _factor_line(factor, text)
    else:
        text.append("  ● nothing alarming in the current model\n", style=TEAL)

    text.append("\n BLAST RADIUS\n", style=f"bold {ACCENT}")
    if file.authors:
        for author in file.authors[:8]:
            name = shorten_middle(clean_text(author.name), 26)
            text.append(f"  {name:<26}", style=TEXT)
            text.append(bar(author.share, 18), style=severity_color(author.share))
            text.append(f" {author.share:>5.1%}  ", style=severity_color(author.share))
            text.append(f"{author.commits} touch{'es' if author.commits != 1 else ''}\n", style=DIM)
    else:
        text.append("  No commit history yet — this file is outside git.\n", style=DIM)

    text.append("\n COMMIT PULSE\n", style=f"bold {ACCENT}")
    text.append("  ")
    text.append_text(_spark_text(file.activity, TEAL))
    text.append("  last 12 months, oldest to newest\n", style=DIM)

    text.append("\n FIRST MOVES\n", style=f"bold {ACCENT}")
    moves = _first_moves(file)
    for index, move in enumerate(moves, start=1):
        text.append(f"  {index}. ", style=f"bold {ACCENT}")
        text.append(f"{move}\n", style=TEXT)

    text.append(
        "\n rot reads existing coverage.xml / lcov.info / coverage.json reports. "
        "It never runs your tests or contacts the network.\n",
        style=DIM,
    )
    return text


def _first_moves(file: FileMetric) -> list[str]:
    moves: list[str] = []
    if file.complexity_score >= 52:
        if file.hot_function:
            moves.append(
                f"Carve {safe(file.hot_function)}() out behind a focused test harness; it carries the steepest branch load."
            )
        else:
            moves.append(
                "Split the densest branch cluster into a named unit before adding more behavior."
            )
    if file.ownership_score >= 52:
        moves.append(
            "Pair a second owner on the next change. A file with one dominant author is a bus-factor incident waiting to happen."
        )
    if file.staleness_score >= 40:
        moves.append(
            "Make a delete / freeze / modernize decision this sprint; age is the risk here, not recent velocity."
        )
    if file.test_hits == 0 and file.coverage is None and not file.is_test:
        moves.append(
            "Pin the public surface with characterization tests; add a coverage report so risk is measured, not guessed."
        )
    if file.churn_score >= 52:
        moves.append(
            "Slow the churn: add a change checklist and route this file through a second reviewer."
        )
    if not moves:
        moves.append("No urgent structural work. Keep the tests green and the boundaries boring.")
    return moves[:3]


def help_text() -> Text:
    text = Text()
    text.append(" rot ", style=f"bold {BACKGROUND_ON_LANG(ACCENT)} on {ACCENT}")
    text.append("  codebase entropy & health inspector\n", style=f"bold {TEXT}")
    text.append(" A local, offline read on where a codebase is getting expensive to change.\n\n", style=MUTED)
    text.append(" KEYS\n", style=f"bold {ACCENT}")
    key_rows = [
        ("↑ ↓", "move through the file leaderboard"),
        ("enter", "open the full file dossier"),
        ("f /", "filter paths (type, then enter)"),
        ("s", "cycle sort: risk, churn, complexity, age, name"),
        ("c", "recolor the entropy map: risk, churn, age, complexity"),
        ("g / G", "jump to the first or last file"),
        ("click", "select a treemap tile"),
        ("r", "rescan the working tree"),
        ("esc", "clear filter / close a dialog"),
        ("?", "this screen"),
        ("q", "quit"),
    ]
    for key, description in key_rows:
        text.append(f"  {key:<9}", style=f"bold {YELLOW}")
        text.append(f"{description}\n", style=TEXT)

    text.append("\n HOW THE ROT INDEX WORKS\n", style=f"bold {ACCENT}")
    text.append(
        "  Rot index blends the weighted risk of the worst fifth of source files (70%) "
        "with the whole tree (30%); higher is worse. Each file combines:\n",
        style=MUTED,
    )
    rows = [
        ("complexity", "31%", "AST cyclomatic load (Python) or token heuristics"),
        ("churn", "25%", "touches, changed lines, and last-90-day velocity"),
        ("ownership", "17%", "concentration of contributions in one author"),
        ("test gap", "13%", "coverage report, or a cautious test-link signal"),
        ("rot", "14%", "time since the last commit"),
    ]
    for name, weight, source in rows:
        text.append(f"  {name:<12}", style=f"bold {TEXT}")
        text.append(f"{weight:>4}  ", style=f"bold {ORANGE}")
        text.append(f"{source}\n", style=MUTED)
    text.append(
        "\n  Synergy bonuses fire when complexity, churn, and single-author ownership "
        "all line up — the classic bus-factor bomb.\n",
        style=MUTED,
    )

    text.append("\n COVERAGE, HONESTLY\n", style=f"bold {ACCENT}")
    text.append(
        "  Exact line coverage comes from coverage.xml, coverage.json, lcov.info, or "
        ".coverage (when coverage.py is installed). No report? rot uses test-file "
        "references as a low-confidence signal, clearly marked. It does not execute tests.\n",
        style=MUTED,
    )

    text.append("\n ENTROPY MAP\n", style=f"bold {ACCENT}")
    text.append(
        "  Tile area is source-line mass; color encodes the selected dimension. "
        "The largest files are drawn so labels remain legible; the rest aggregate into "
        "one neutral tile. Press c to change the lens.\n",
        style=MUTED,
    )
    text.append("\n esc / q / ? to close\n", style=f"bold {DIM}")
    return text
