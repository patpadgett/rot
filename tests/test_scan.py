"""The scan pipeline ties analysis, git history, coverage, and summaries together."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import DAY, NOW, RepoBuilder
from rot.scan import scan_repository


def _write_coverage(root: Path) -> None:
    (root / "coverage.xml").write_text(
        """<?xml version="1.0" ?>
<coverage>
  <packages><package><classes>
    <class filename="service/app.py" line-rate="0.75"/>
    <class filename="service/util.py" line-rate="0.5"/>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )


def test_scan_combines_every_signal(repo: RepoBuilder):
    _write_coverage(repo.root)
    snapshot = scan_repository(repo.root, now=NOW)
    summary = snapshot.summary
    by_path = {file.path: file for file in snapshot.files}

    assert summary.name == "sample"
    assert summary.branch == "main"
    assert summary.commits == 3
    assert summary.authors == 2
    assert summary.files == 5
    assert summary.history_files == 5
    assert summary.bus_factor == 1
    assert summary.bus_share == pytest.approx(2 / 3)
    assert summary.stale_files == 1
    assert summary.stale_pct == 25.0
    assert summary.coverage_files == 2
    assert summary.coverage_mode == "report"
    assert summary.scanned_at == NOW
    assert summary.scan_ms > 0
    assert not summary.history_limit_reached

    assert set(by_path) == {
        "service/app.py",
        "service/util.py",
        "legacy/currency.py",
        "web/view.ts",
        "tests/test_app.py",
    }
    assert by_path["service/app.py"].coverage == 0.75
    assert by_path["service/app.py"].coverage_source == "coverage.xml"
    assert by_path["service/util.py"].coverage == 0.5
    assert by_path["tests/test_app.py"].is_test is True
    assert by_path["tests/test_app.py"].coverage is None
    assert by_path["service/app.py"].test_hits == 1
    assert by_path["legacy/currency.py"].last_commit is not None
    assert by_path["service/app.py"].authors[0].name in {"Ada Lovelace", "Grace Hopper"}
    # Newest commits first: the app file was last touched by Grace.
    assert by_path["service/app.py"].last_author == "Grace Hopper"


def test_scan_marks_untracked_and_dirty_files(repo: RepoBuilder):
    (repo.root / "service" / "app.py").write_text("changed\n", encoding="utf-8")
    (repo.root / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    snapshot = scan_repository(repo.root, now=NOW)
    by_path = {file.path: file for file in snapshot.files}
    assert by_path["service/app.py"].dirty is True
    assert by_path["service/app.py"].untracked is False
    assert by_path["scratch.py"].untracked is True
    assert snapshot.summary.dirty_files >= 1
    assert snapshot.summary.untracked_files == 1


def test_scan_uses_test_link_heuristic_without_coverage(repo: RepoBuilder):
    snapshot = scan_repository(repo.root, now=NOW)
    assert snapshot.summary.coverage_mode == "linked"
    assert snapshot.summary.coverage_files == 0
    app = next(file for file in snapshot.files if file.path == "service/app.py")
    assert app.test_hits == 1
    assert app.coverage is None
    # The heuristic remains visibly labelled as a link signal, not coverage.
    assert app.test_score == 100 * min(0.78, 0.22 + 0.12)


def test_scan_reports_no_test_signal(repo: RepoBuilder):
    (repo.root / "tests" / "test_app.py").unlink()
    snapshot = scan_repository(repo.root, now=NOW)
    assert snapshot.summary.coverage_mode == "none"
    app = next(file for file in snapshot.files if file.path == "service/app.py")
    assert app.test_hits == 0
    assert any(factor.key == "tests" for factor in app.factors)


def test_scan_respects_max_files_and_warns(repo: RepoBuilder):
    snapshot = scan_repository(repo.root, max_files=2, now=NOW)
    assert snapshot.summary.files == 2
    assert any("showing 2 of 5 source files" in warning for warning in snapshot.summary.warnings)


def test_scan_handles_empty_and_uncommitted_repositories(tmp_path: Path):
    builder = RepoBuilder(tmp_path / "empty")
    builder.write("README.md", "not source\n")
    snapshot = scan_repository(builder.root, now=NOW)
    assert snapshot.summary.files == 0
    assert snapshot.summary.commits == 0
    assert any("no supported source files" in item for item in snapshot.summary.warnings)
    assert any("no commits yet" in item for item in snapshot.summary.warnings)

    builder.write("app.py", "def run():\n    return 1\n")
    snapshot = scan_repository(builder.root, now=NOW)
    assert snapshot.summary.files == 1
    metric = snapshot.files[0]
    assert metric.untracked is True
    assert metric.commits == 0
    assert metric.risk > 17.0
    assert any(factor.key == "untracked" for factor in metric.factors)


def test_scan_is_deterministic_for_a_fixed_clock(repo: RepoBuilder):
    first = scan_repository(repo.root, now=NOW)
    second = scan_repository(repo.root, now=NOW)
    assert [file.path for file in first.files] == [file.path for file in second.files]
    assert [file.risk for file in first.files] == [file.risk for file in second.files]
    assert first.summary.risk_index == second.summary.risk_index
    assert first.summary.stale_files == second.summary.stale_files
    assert abs(first.summary.scan_ms - second.summary.scan_ms) < 5_000


def test_scan_ignores_vendor_directories(tmp_path: Path):
    builder = RepoBuilder(tmp_path / "vendored")
    builder.write("app.py", "x = 1\n")
    builder.write("node_modules/pkg/index.js", "if (x) {}\n")
    builder.write(".venv/lib/site.py", "x = 1\n")
    builder.commit("initial", timestamp=NOW - DAY)
    snapshot = scan_repository(builder.root, now=NOW)
    assert [file.path for file in snapshot.files] == ["app.py"]
