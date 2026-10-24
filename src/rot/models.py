"""Data structures shared by the scanners and the interface."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthorShare:
    """One author's slice of a file's change history."""

    name: str
    email: str
    commits: int
    share: float = 0.0


@dataclass(slots=True)
class RiskFactor:
    """A human-readable reason a file scored the way it did."""

    key: str
    label: str
    detail: str
    severity: float


@dataclass(slots=True)
class FileMetric:
    """Everything rot knows about a single source file."""

    path: str
    language: str
    loc: int = 0
    sloc: int = 0
    size: int = 0

    # Static analysis.
    total_complexity: int = 1
    max_complexity: int = 1
    functions: int = 0
    classes: int = 0
    max_depth: int = 0
    hot_function: str = ""
    parse_error: bool = False

    # Git history.
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    recent_commits: int = 0
    recent_lines: int = 0
    authors: list[AuthorShare] = field(default_factory=list)
    last_commit: float | None = None
    first_commit: float | None = None
    last_author: str = ""
    activity: list[int] = field(default_factory=lambda: [0] * 12)
    untracked: bool = False
    dirty: bool = False

    # Tests and coverage.
    is_test: bool = False
    test_hits: int = 0
    test_files: list[str] = field(default_factory=list)
    coverage: float | None = None
    coverage_source: str = ""

    # Scores, normalized to 0..100.
    risk: float = 0.0
    complexity_score: float = 0.0
    churn_score: float = 0.0
    ownership_score: float = 0.0
    staleness_score: float = 0.0
    test_score: float = 0.0
    factors: list[RiskFactor] = field(default_factory=list)

    @property
    def primary_author(self) -> AuthorShare | None:
        return self.authors[0] if self.authors else None

    @property
    def author_count(self) -> int:
        return len(self.authors)

    @property
    def churn(self) -> int:
        return self.insertions + self.deletions

    @property
    def directory(self) -> str:
        head, sep, _ = self.path.rpartition("/")
        return head if sep else "."

    @property
    def filename(self) -> str:
        return self.path.rpartition("/")[2]

    def age_days(self, now: float) -> float | None:
        if self.last_commit is None:
            return None
        return max(0.0, (now - self.last_commit) / 86_400)

    def test_value(self) -> float | None:
        """Best available test signal, 0..1.

        A real coverage report wins.  Otherwise this is a deliberately
        conservative link heuristic, not an estimate of executed lines.
        """
        if self.coverage is not None:
            return self.coverage
        if self.test_hits:
            return min(0.85, 0.2 + 0.14 * self.test_hits)
        return 0.0

    def test_label(self) -> str:
        if self.coverage is not None:
            return f"{self.coverage * 100:.0f}%"
        if self.test_hits:
            return f"~{min(99, self.test_score):.0f}%"
        return "—"

    def grade(self) -> str:
        if self.risk >= 72:
            return "critical"
        if self.risk >= 54:
            return "high"
        if self.risk >= 34:
            return "medium"
        if self.risk >= 18:
            return "low"
        return "calm"

    def factors_for_display(self, limit: int = 4) -> list[RiskFactor]:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            self.factors,
            key=lambda factor: (-factor.severity, order.get(factor.key, 9)),
        )[:limit]


@dataclass(slots=True)
class RepoSummary:
    """Repository-wide roll-up."""

    root: str
    name: str
    branch: str
    head: str
    files: int = 0
    loc: int = 0
    sloc: int = 0
    commits: int = 0
    authors: int = 0
    history_files: int = 0
    recent_commits: int = 0
    recent_lines: int = 0
    first_commit: float | None = None
    last_commit: float | None = None
    dirty_files: int = 0
    untracked_files: int = 0

    risk_index: float = 0.0
    health: float = 100.0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    stale_files: int = 0
    stale_pct: float = 0.0
    bus_factor: int = 0
    bus_share: float = 0.0

    coverage_files: int = 0
    coverage_mode: str = "none"
    history_limit_reached: bool = False
    max_commits: int = 0
    scan_ms: float = 0.0
    scanned_at: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def risk_grade(self) -> str:
        if self.risk_index >= 72:
            return "critical"
        if self.risk_index >= 54:
            return "high"
        if self.risk_index >= 34:
            return "medium"
        if self.risk_index >= 18:
            return "low"
        return "calm"


@dataclass(slots=True)
class Snapshot:
    summary: RepoSummary
    files: list[FileMetric]
    now: float

    def sorted_files(self, mode: str = "risk") -> list[FileMetric]:
        rows = list(self.files)
        if mode == "churn":
            rows.sort(key=lambda f: (f.commits, f.churn), reverse=True)
        elif mode == "complexity":
            rows.sort(
                key=lambda f: (f.max_complexity, f.total_complexity, f.sloc),
                reverse=True,
            )
        elif mode == "age":
            rows.sort(
                key=lambda f: (
                    f.age_days(self.now) if f.last_commit is not None else 10**9
                ),
                reverse=True,
            )
        elif mode == "name":
            rows.sort(key=lambda f: f.path)
        else:
            rows.sort(
                key=lambda f: (f.risk, f.complexity_score, f.commits),
                reverse=True,
            )
        return rows
