"""Risk scoring, test-gap behavior, repo roll-ups, and bus factor."""

from __future__ import annotations

import pytest

from rot.models import AuthorShare, FileMetric
from rot.score import (
    bus_factor,
    churn_score,
    complexity_score,
    compute_risk_index,
    ownership_score,
    score_files,
    staleness_score,
)

NOW = 1_750_000_000.0
DAY = 86_400.0


def make_file(**kwargs) -> FileMetric:
    base = dict(path="src/app.py", language="python", sloc=100, loc=120)
    base.update(kwargs)
    return FileMetric(**base)


def test_bus_factor_thresholds():
    assert bus_factor({}) == (0, 0.0)
    assert bus_factor({"ada": 100}) == (1, 1.0)
    assert bus_factor({"ada": 50, "grace": 30, "linus": 20}) == (1, 0.5)
    assert bus_factor({"ada": 40, "grace": 30, "linus": 30}) == (2, 0.7)


def test_untested_file_gets_the_full_test_gap():
    metric = make_file()
    score_files([metric], NOW)
    assert metric.test_score == 0.0
    assert metric.risk == pytest.approx(18.3)
    assert [factor.key for factor in metric.factors] == ["tests"]


def test_test_files_do_not_receive_test_gap_penalties():
    source = make_file(path="service/app.py")
    test = make_file(path="tests/test_app.py", is_test=True)
    score_files([source, test], NOW)
    assert source.risk == pytest.approx(18.3)
    assert test.risk == pytest.approx(5.3)
    assert not any(factor.key == "tests" for factor in test.factors)


def test_real_coverage_closes_the_test_gap():
    metric = make_file(coverage=1.0, coverage_source="coverage.xml")
    score_files([metric], NOW)
    assert metric.test_score == 100.0
    assert metric.risk == pytest.approx(5.3)
    assert not metric.factors


def test_authors_are_ranked_and_shares_are_normalized():
    metric = make_file(
        commits=10,
        authors=[
            AuthorShare(name="Grace", email="grace@example.com", commits=2),
            AuthorShare(name="Ada", email="ada@example.com", commits=8),
        ],
    )
    score_files([metric], NOW)
    assert [author.name for author in metric.authors] == ["Ada", "Grace"]
    assert [author.share for author in metric.authors] == [0.8, 0.2]
    assert metric.ownership_score > 50


def test_synergy_fires_for_complex_high_churn_single_owner_file():
    metric = make_file(
        sloc=1_500,
        max_complexity=20,
        total_complexity=150,
        commits=35,
        insertions=2_500,
        deletions=2_500,
        recent_commits=8,
        authors=[AuthorShare(name="Ada", email="ada@example.com", commits=35)],
        coverage=1.0,
        last_commit=NOW,
    )
    score_files([metric], NOW)
    assert metric.complexity_score == 100.0
    assert metric.churn_score == 100.0
    assert metric.ownership_score == 100.0
    # 31 + 25 + 17 from the base weights, plus the 7-point synergy bonus.
    assert metric.risk == 80.0


def test_staleness_ramps_after_four_months():
    recent = make_file(last_commit=NOW - 100 * DAY)
    stale = make_file(last_commit=NOW - 1_020 * DAY)
    score_files([recent, stale], NOW)
    assert recent.staleness_score == 0.0
    assert 99 < stale.staleness_score <= 100
    assert stale.risk > recent.risk


def test_component_scores_are_monotonic():
    small = make_file(sloc=20, max_complexity=2, total_complexity=3)
    large = make_file(sloc=2_000, max_complexity=40, total_complexity=300)
    assert complexity_score(large) > complexity_score(small)

    quiet = make_file(commits=1, insertions=2, deletions=1)
    busy = make_file(
        commits=80,
        insertions=9_000,
        deletions=3_000,
        recent_commits=20,
    )
    assert churn_score(busy) > churn_score(quiet)

    sole = make_file(
        commits=40,
        authors=[AuthorShare("Ada", "ada@example.com", 40, share=1.0)],
    )
    shared = make_file(
        commits=40,
        authors=[
            AuthorShare("Ada", "ada@example.com", 20, share=0.5),
            AuthorShare("Grace", "grace@example.com", 20, share=0.5),
        ],
    )
    assert ownership_score(sole) > ownership_score(shared)
    assert staleness_score(large, NOW) == 0.0


def test_risk_index_uses_the_worst_fifth_and_ignores_tests():
    files = [
        make_file(path=f"src/f{index}.py", risk=risk, sloc=100)
        for index, risk in enumerate((90, 80, 70, 10, 0))
    ]
    files.append(make_file(path="tests/test_app.py", risk=99, sloc=100, is_test=True))
    index, health = compute_risk_index(files)
    # Top three of five source files average 80; the whole tree averages 50.
    assert index == 71.0
    assert health == 29.0


def test_risk_index_empty_tree_is_healthy():
    assert compute_risk_index([]) == (0.0, 100.0)
    assert compute_risk_index([make_file(sloc=0)]) == (0.0, 100.0)
