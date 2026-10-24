"""Git metadata, file listing, and single-pass history extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import DAY, NOW, RepoBuilder
from rot.git_history import (
    GitError,
    find_repo,
    list_files,
    read_history,
    repo_metadata,
)


def test_find_repo_from_nested_directory(repo: RepoBuilder):
    nested = repo.root / "service"
    assert find_repo(nested) == repo.root.resolve()
    assert find_repo(repo.root / "service" / "app.py") == repo.root.resolve()


def test_find_repo_rejects_non_repository(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(GitError, match="not a git repository"):
        find_repo(tmp_path / "plain")


def test_repo_metadata(repo: RepoBuilder):
    meta = repo_metadata(repo.root)
    assert meta.root == repo.root.resolve()
    assert meta.name == "sample"
    assert meta.branch == "main"
    assert meta.commits == 3
    assert meta.head != "no commits"


def test_empty_repository_metadata(tmp_path: Path):
    builder = RepoBuilder(tmp_path / "empty")
    meta = repo_metadata(builder.root)
    assert meta.commits == 0
    assert meta.head == "no commits"


def test_list_files_tracks_dirty_and_untracked(repo: RepoBuilder):
    paths, tracked, dirty = list_files(repo.root)
    assert "service/app.py" in paths
    assert "service/app.py" in tracked
    assert "web/view.ts" in tracked
    assert dirty == set()

    (repo.root / "service" / "app.py").write_text("changed\n", encoding="utf-8")
    (repo.root / "scratch.py").write_text("new\n", encoding="utf-8")
    paths, tracked, dirty = list_files(repo.root)
    assert "scratch.py" in paths
    assert "scratch.py" not in tracked
    assert "service/app.py" in dirty
    assert "scratch.py" not in dirty  # untracked is reported separately


def test_read_history_counts_files_authors_and_recent_activity(repo: RepoBuilder):
    history = read_history(repo.root, now=NOW)
    assert history.commits_loaded == 3
    assert history.authors == {"ada@example.com": 2, "grace@example.com": 1}
    assert history.recent_commits == 2
    assert history.recent_lines > 0
    assert history.first_commit == pytest.approx(NOW - 400 * DAY)
    assert history.last_commit == pytest.approx(NOW - 10 * DAY)

    app = history.files["service/app.py"]
    assert app.commits == 2
    assert app.insertions > 0
    assert app.deletions > 0
    assert app.recent_commits == 1
    assert {author.name for author in app.authors.values()} == {"Ada Lovelace", "Grace Hopper"}
    assert app.first_commit == pytest.approx(NOW - 400 * DAY)
    assert app.last_commit == pytest.approx(NOW - 30 * DAY)
    assert app.last_author == "Grace Hopper"
    assert app.activity[-1] == 1  # the most recent 30-day bucket

    util = history.files["service/util.py"]
    assert util.commits == 2
    assert util.recent_commits == 1


def test_read_history_interest_filter_keeps_repo_totals(repo: RepoBuilder):
    history = read_history(repo.root, now=NOW, interest={"service/app.py"})
    assert set(history.files) == {"service/app.py"}
    assert history.files["service/app.py"].commits == 2
    assert history.recent_commits == 2
    assert history.authors == {"ada@example.com": 2, "grace@example.com": 1}


def test_read_history_honors_commit_cap(repo: RepoBuilder):
    history = read_history(repo.root, max_commits=1, now=NOW)
    assert history.commits_loaded == 1
    assert history.authors == {"ada@example.com": 1}
    assert set(history.files) == {"service/util.py"}


def test_read_history_on_empty_repo(tmp_path: Path):
    builder = RepoBuilder(tmp_path / "empty")
    history = read_history(builder.root, now=NOW)
    assert history.commits_loaded == 0
    assert history.files == {}
    assert history.authors == {}
