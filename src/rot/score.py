"""The scoring model: turn static metrics and history into rot risk."""

from __future__ import annotations

import math
from statistics import fmean

from .format import human_age
from .models import FileMetric, RiskFactor


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _log_scale(value: float, ceiling: float) -> float:
    if value <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log1p(value) / math.log1p(ceiling)))


def complexity_score(file: FileMetric) -> float:
    hot = min(1.0, file.max_complexity / 20.0)
    mass = _log_scale(file.total_complexity, 150)
    size = _log_scale(file.sloc, 1_500)
    return _clamp((0.62 * hot + 0.20 * mass + 0.18 * size) * 100)


def churn_score(file: FileMetric) -> float:
    touches = _log_scale(file.commits, 35)
    lines = _log_scale(file.churn, 5_000)
    recent = min(1.0, file.recent_commits / 8.0)
    return _clamp((0.55 * touches + 0.22 * lines + 0.23 * recent) * 100)


def ownership_score(file: FileMetric) -> float:
    if not file.authors or file.commits == 0:
        return 0.0
    primary = file.primary_author
    share = primary.share if primary else 0.0
    evidence = min(1.0, math.log1p(file.commits) / math.log(8))
    concentration = share ** 1.15
    return _clamp(concentration * evidence * 100)


def staleness_score(file: FileMetric, now: float) -> float:
    if file.last_commit is None:
        return 0.0
    days = (now - file.last_commit) / 86_400
    if days <= 120:
        return 0.0
    return _clamp((days - 120) / 900 * 100)


def _test_signal(file: FileMetric) -> float:
    if file.coverage is not None:
        return _clamp(file.coverage, 0.0, 1.0)
    if file.test_hits:
        return min(0.78, 0.22 + 0.12 * file.test_hits)
    return 0.0


def _factors(file: FileMetric, now: float, test_gap: float) -> list[RiskFactor]:
    factors: list[RiskFactor] = []
    primary = file.primary_author
    if file.complexity_score >= 42:
        if file.hot_function:
            detail = f"{file.hot_function}() peaks at CC {file.max_complexity}"
        else:
            detail = f"{file.max_complexity} decision branch{'es' if file.max_complexity != 1 else ''} in one file"
        factors.append(
            RiskFactor(
                key="complexity",
                label="Cyclomatic hotspot",
                detail=detail,
                severity=file.complexity_score / 100,
            )
        )
    if file.max_depth >= 5:
        factors.append(
            RiskFactor(
                key="depth",
                label="Deep nesting",
                detail=f"{file.max_depth} levels of nesting",
                severity=min(1.0, 0.45 + (file.max_depth - 5) * 0.08),
            )
        )
    if file.sloc >= 650:
        factors.append(
            RiskFactor(
                key="mega-file",
                label="Mega-file",
                detail=f"{file.sloc:,} source lines in one file",
                severity=min(1.0, 0.45 + file.sloc / 5_000),
            )
        )
    if file.churn_score >= 42:
        detail = f"{file.commits} touches · {file.churn:,} changed lines"
        if file.recent_commits:
            detail += f" · {file.recent_commits} in 90d"
        factors.append(
            RiskFactor(
                key="churn",
                label="High-churn surface",
                detail=detail,
                severity=file.churn_score / 100,
            )
        )
    if file.ownership_score >= 40 and file.commits >= 3 and primary:
        factors.append(
            RiskFactor(
                key="ownership",
                label="Bus-factor risk",
                detail=f"{primary.name} owns {primary.share:.0%} of {file.commits} touches",
                severity=min(1.0, file.ownership_score / 100),
            )
        )
    if file.staleness_score >= 28:
        factors.append(
            RiskFactor(
                key="stale",
                label="Code rot",
                detail=f"untouched for {human_age(file.last_commit, now, long=True)}",
                severity=min(1.0, file.staleness_score / 100),
            )
        )
    if test_gap >= 55 and not file.is_test:
        if file.coverage is not None:
            detail = f"{file.coverage:.0%} line coverage ({file.coverage_source})"
        elif file.test_hits:
            detail = f"link signal only · {file.test_hits} test reference{'s' if file.test_hits != 1 else ''}"
        else:
            detail = "no test references found"
        factors.append(
            RiskFactor(
                key="tests",
                label="Test blind spot",
                detail=detail,
                severity=test_gap / 100,
            )
        )
    if file.untracked:
        factors.append(
            RiskFactor(
                key="untracked",
                label="Uncommitted",
                detail="outside git history",
                severity=0.3,
            )
        )
    if file.parse_error:
        factors.append(
            RiskFactor(
                key="parse",
                label="Parse error",
                detail="structural metrics are approximate",
                severity=0.25,
            )
        )
    if file.dirty:
        factors.append(
            RiskFactor(
                key="dirty",
                label="Uncommitted edits",
                detail="working tree has local changes",
                severity=0.16,
            )
        )
    return factors


def score_files(files: list[FileMetric], now: float) -> None:
    for file in files:
        # Author shares are display data as well as the ownership input.
        for author in file.authors:
            author.share = author.commits / file.commits if file.commits else 0.0
        file.authors.sort(key=lambda author: author.commits, reverse=True)

        file.complexity_score = complexity_score(file)
        file.churn_score = churn_score(file)
        file.ownership_score = ownership_score(file)
        file.staleness_score = staleness_score(file, now)
        test_signal = _test_signal(file)
        file.test_score = test_signal * 100
        test_gap = 0.0 if file.is_test else (1.0 - test_signal) * 100

        risk = (
            0.31 * file.complexity_score
            + 0.25 * file.churn_score
            + 0.17 * file.ownership_score
            + 0.13 * test_gap
            + 0.14 * file.staleness_score
        )
        synergy = 0.0
        if (
            file.complexity_score >= 55
            and file.churn_score >= 55
            and file.ownership_score >= 55
        ):
            synergy += 7.0
        if file.complexity_score >= 55 and file.staleness_score >= 55:
            synergy += 5.0
        if test_gap >= 70 and file.complexity_score >= 60:
            synergy += 3.0
        if file.untracked:
            risk += 4.0
        if file.parse_error:
            risk += 2.0
        file.risk = round(_clamp(risk + synergy, 0, 99.5), 1)
        file.factors = _factors(file, now, test_gap)


def compute_risk_index(files: list[FileMetric]) -> tuple[float, float]:
    """Return (rot_index, health).  Tests are listed but don't dominate health."""
    source = [file for file in files if not file.is_test and file.sloc > 0]
    if not source:
        source = [file for file in files if file.sloc > 0] or list(files)
    if not source:
        return 0.0, 100.0

    ranked = sorted(source, key=lambda file: file.risk, reverse=True)
    top_n = max(3, math.ceil(len(ranked) * 0.2))
    top = ranked[:top_n]

    def weighted_average(rows: list[FileMetric]) -> float:
        weights = [max(1.0, file.sloc) ** 0.5 for file in rows]
        total = sum(weights)
        if not total:
            return fmean([file.risk for file in rows]) if rows else 0.0
        return sum(file.risk * weight for file, weight in zip(rows, weights)) / total

    top_risk = weighted_average(top)
    overall = weighted_average(source)
    index = _clamp(0.70 * top_risk + 0.30 * overall)
    return round(index, 1), round(100.0 - index, 1)


def bus_factor(authors: dict[str, int]) -> tuple[int, float]:
    counts = sorted(authors.values(), reverse=True)
    total = sum(counts)
    if not total:
        return 0, 0.0
    covered = 0
    for index, count in enumerate(counts, start=1):
        covered += count
        if covered >= total * 0.5:
            return index, covered / total
    return len(counts), 1.0
