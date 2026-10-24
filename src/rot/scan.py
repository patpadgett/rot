"""The pipeline that turns a git checkout into one Snapshot."""

from __future__ import annotations

import time
from pathlib import Path

from .analyze import (
    is_candidate,
    is_test_path,
    link_tests,
    analyze_file,
)
from .coverage_data import load_coverage
from .git_history import find_repo, list_files, read_history, repo_metadata
from .models import FileMetric, RepoSummary, Snapshot
from .score import bus_factor, compute_risk_index, score_files


def scan_repository(
    path: str | Path = ".",
    *,
    max_commits: int = 5_000,
    max_files: int = 6_000,
    now: float | None = None,
) -> Snapshot:
    started = time.perf_counter()
    now = time.time() if now is None else float(now)
    source_path = Path(path).expanduser()
    root = find_repo(source_path)
    metadata = repo_metadata(root)
    paths, tracked, dirty = list_files(root)
    candidates = sorted({item for item in paths if is_candidate(item)})
    warnings: list[str] = []

    history = read_history(
        root,
        max_commits=max_commits,
        now=now,
        interest=set(candidates),
    )
    if len(candidates) > max_files:
        candidates.sort(
            key=lambda item: (
                -history.files[item].commits if item in history.files else 0,
                item,
            )
        )
        warnings.append(
            f"showing {max_files:,} of {len(candidates):,} source files; "
            "raise --max-files to scan them all"
        )
        candidates = candidates[:max_files]
    candidates.sort()

    files: list[FileMetric] = []
    skipped = 0
    for path_name in candidates:
        metric = analyze_file(root, path_name)
        if metric is None:
            skipped += 1
            continue
        metric.is_test = is_test_path(path_name)
        metric.untracked = path_name not in tracked
        metric.dirty = path_name in dirty
        file_history = history.files.get(path_name)
        if file_history:
            metric.commits = file_history.commits
            metric.insertions = file_history.insertions
            metric.deletions = file_history.deletions
            metric.recent_commits = file_history.recent_commits
            metric.recent_lines = file_history.recent_lines
            metric.authors = list(file_history.authors.values())
            metric.last_commit = file_history.last_commit
            metric.first_commit = file_history.first_commit
            metric.last_author = file_history.last_author
            metric.activity = list(file_history.activity)
        files.append(metric)

    coverage_map, coverage_source = load_coverage(root)
    coverage_matches = 0
    if coverage_map:
        by_name: dict[str, list[tuple[str, tuple[float, str]]]] = {}
        for candidate, value in coverage_map.items():
            by_name.setdefault(candidate.rsplit("/", 1)[-1], []).append((candidate, value))
        for metric in files:
            found = coverage_map.get(metric.path)
            if found is None:
                # Coverage tools sometimes report a path with an extra source
                # prefix.  Only accept unambiguous suffix matches.
                for candidate, value in by_name.get(metric.filename, ()):
                    if metric.path.endswith("/" + candidate):
                        found = value
                        break
            if found is not None:
                metric.coverage, metric.coverage_source = found
                coverage_matches += 1
        if not coverage_matches:
            warnings.append(
                f"found {coverage_source} but its paths did not match the checkout"
            )

    linked_sources = link_tests(files, root)
    score_files(files, now)

    source_files = [file for file in files if not file.is_test] or files
    critical = sum(1 for file in source_files if file.risk >= 72)
    high = sum(1 for file in source_files if 54 <= file.risk < 72)
    medium = sum(1 for file in source_files if 34 <= file.risk < 54)
    low = sum(1 for file in source_files if 18 <= file.risk < 34)
    history_files = [file for file in source_files if file.last_commit is not None]
    stale_files = [
        file
        for file in history_files
        if (now - (file.last_commit or now)) / 86_400 >= 365
    ]
    stale_pct = (len(stale_files) / len(history_files) * 100) if history_files else 0.0
    risk_index, health = compute_risk_index(files)
    factor, bus_share = bus_factor(history.authors)

    history.truncated = metadata.commits > history.commits_loaded
    if history.truncated:
        warnings.append(
            f"history capped at {max_commits:,} commits; "
            "author and churn totals are a window"
        )
    if not files:
        warnings.append("no supported source files found")
    if metadata.commits == 0:
        warnings.append("repository has no commits yet")
    if skipped:
        warnings.append(f"{skipped} unreadable or oversized source files skipped")

    coverage_files = sum(
        1 for file in source_files if file.coverage is not None
    )
    if coverage_files:
        coverage_mode = "report"
    elif linked_sources:
        coverage_mode = "linked"
    else:
        coverage_mode = "none"

    elapsed = time.perf_counter() - started
    summary = RepoSummary(
        root=str(root),
        name=metadata.name,
        branch=metadata.branch,
        head=metadata.head,
        files=len(files),
        loc=sum(file.loc for file in files),
        sloc=sum(file.sloc for file in files),
        commits=metadata.commits,
        authors=len(history.authors),
        history_files=len(history.files),
        recent_commits=history.recent_commits,
        recent_lines=history.recent_lines,
        first_commit=history.first_commit,
        last_commit=history.last_commit,
        dirty_files=sum(1 for file in files if file.dirty),
        untracked_files=sum(1 for file in files if file.untracked),
        risk_index=risk_index,
        health=health,
        critical=critical,
        high=high,
        medium=medium,
        low=low,
        stale_files=len(stale_files),
        stale_pct=stale_pct,
        bus_factor=factor,
        bus_share=bus_share,
        coverage_files=coverage_files,
        coverage_mode=coverage_mode,
        history_limit_reached=history.truncated,
        max_commits=max_commits,
        scan_ms=elapsed * 1_000,
        scanned_at=now,
        warnings=warnings,
    )
    return Snapshot(summary=summary, files=files, now=now)
