"""Fast, dependency-free extraction of git history and repository metadata."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .models import AuthorShare


class GitError(RuntimeError):
    pass


@dataclass(slots=True)
class RepoMetadata:
    root: Path
    name: str
    branch: str
    head: str
    commits: int


@dataclass(slots=True)
class FileHistory:
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    recent_commits: int = 0
    recent_lines: int = 0
    authors: dict[str, AuthorShare] = field(default_factory=dict)
    last_commit: float | None = None
    first_commit: float | None = None
    last_author: str = ""
    activity: list[int] = field(default_factory=lambda: [0] * 12)


@dataclass(slots=True)
class HistoryData:
    files: dict[str, FileHistory] = field(default_factory=dict)
    commits_loaded: int = 0
    authors: dict[str, int] = field(default_factory=dict)
    recent_commits: int = 0
    recent_lines: int = 0
    first_commit: float | None = None
    last_commit: float | None = None
    truncated: bool = False


def _git(
    root: Path,
    *args: str,
    check: bool = True,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitError(f"could not run git: {error}") from error
    if check and result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return result


def find_repo(path: Path) -> Path:
    start = path.resolve()
    if not start.exists():
        raise GitError(f"path does not exist: {path}")
    if start.is_file():
        start = start.parent
    result = _git(start, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise GitError(f"not a git repository: {start}")
    root = Path(os.fsdecode(result.stdout.strip()))
    inside = _git(root, "rev-parse", "--is-inside-work-tree", check=False)
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        raise GitError(f"not a git working tree: {root}")
    return root


def repo_metadata(root: Path) -> RepoMetadata:
    branch_result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    head_result = _git(root, "rev-parse", "--short", "HEAD", check=False)
    count_result = _git(
        root, "rev-list", "--count", "--no-merges", "HEAD", check=False
    )
    branch = (
        os.fsdecode(branch_result.stdout.strip())
        if branch_result.returncode == 0 and branch_result.stdout.strip()
        else "detached"
    )
    head = (
        os.fsdecode(head_result.stdout.strip())
        if head_result.returncode == 0
        else "no commits"
    )
    try:
        commits = int(count_result.stdout.strip() or b"0")
    except ValueError:
        commits = 0
    return RepoMetadata(
        root=root,
        name=root.name or str(root),
        branch=branch,
        head=head,
        commits=commits,
    )


def _path_list(root: Path, *args: str) -> list[str]:
    result = _git(root, "ls-files", "-z", *args, check=False)
    if result.returncode != 0:
        return []
    paths = [os.fsdecode(item) for item in result.stdout.split(b"\x00") if item]
    return paths


def list_files(root: Path) -> tuple[list[str], set[str], set[str]]:
    """Return tracked + untracked files, tracked paths, and dirty paths."""
    all_files = _path_list(root, "--cached", "--others", "--exclude-standard")
    tracked = set(_path_list(root, "--cached"))
    dirty: set[str] = set()
    status = _git(root, "status", "--porcelain=v1", "-z", "-uno", check=False)
    if status.returncode == 0:
        parts = status.stdout.split(b"\x00")
        index = 0
        while index < len(parts):
            entry = parts[index]
            index += 1
            if len(entry) < 4:
                continue
            code = entry[:2]
            path = os.fsdecode(entry[3:])
            dirty.add(path)
            if b"R" in code or b"C" in code:
                if index < len(parts) and parts[index]:
                    dirty.add(os.fsdecode(parts[index]))
                    index += 1
    return sorted(set(all_files)), tracked, dirty


def _activity_bucket(timestamp: float, now: float) -> int | None:
    age_days = (now - timestamp) / 86_400
    if age_days >= 366:
        return None
    if age_days < 0:
        return 11
    return 11 - min(11, int(age_days // 30.5))


def read_history(
    root: Path,
    *,
    max_commits: int = 5_000,
    now: float | None = None,
    interest: set[str] | None = None,
) -> HistoryData:
    """Read a whole repo's history in one git process.

    ``interest`` limits per-file bookkeeping to files rot will actually show;
    repository-level author and churn counts are still collected.
    """
    now = time.time() if now is None else now
    history = HistoryData()
    recent_cutoff = now - 90 * 86_400
    result = _git(
        root,
        "-c",
        "core.quotepath=false",
        "-c",
        "log.showSignature=false",
        "log",
        "--no-merges",
        "--date-order",
        "--no-decorate",
        "--numstat",
        "--format=%x1e%H%x1f%an%x1f%ae%x1f%ct",
        "-n",
        str(max_commits),
        "HEAD",
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        return history

    text = result.stdout.decode("utf-8", errors="replace")
    commit_ts = 0.0
    author_name = ""
    author_email = ""
    current_commit_seen = False
    file_activity_seen: set[str] = set()

    # str.splitlines() treats \x1e (our commit separator) as a line break,
    # so split only on real newlines here.
    for line in text.split("\n"):
        if line.startswith("\x1e"):
            current_commit_seen = True
            history.commits_loaded += 1
            fields = line[1:].split("\x1f")
            if len(fields) >= 4:
                try:
                    commit_ts = float(fields[3])
                except ValueError:
                    commit_ts = 0.0
                author_name = fields[1]
                author_email = fields[2]
            else:
                commit_ts = 0.0
            author_key = (author_email or author_name).strip().lower()
            history.authors[author_key] = history.authors.get(author_key, 0) + 1
            if commit_ts >= recent_cutoff:
                history.recent_commits += 1
            if commit_ts:
                history.first_commit = (
                    commit_ts
                    if history.first_commit is None
                    else min(history.first_commit, commit_ts)
                )
                history.last_commit = (
                    commit_ts
                    if history.last_commit is None
                    else max(history.last_commit, commit_ts)
                )
            file_activity_seen.clear()
            continue

        if not current_commit_seen or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_text, removed_text = parts[0], parts[1]
        path = "\t".join(parts[2:]).rstrip("\r")
        if not path:
            continue
        try:
            added = int(added_text) if added_text != "-" else 0
            removed = int(removed_text) if removed_text != "-" else 0
        except ValueError:
            added = removed = 0
        if commit_ts >= recent_cutoff:
            history.recent_lines += added + removed
        if interest is not None and path not in interest:
            continue
        entry = history.files.setdefault(path, FileHistory())
        if path not in file_activity_seen:
            entry.commits += 1
            entry.insertions += added
            entry.deletions += removed
            author_key = (author_email or author_name).strip().lower()
            author = entry.authors.get(author_key)
            if author is None:
                entry.authors[author_key] = AuthorShare(
                    name=author_name or "unknown",
                    email=author_email,
                    commits=1,
                )
            else:
                author.commits += 1
                if author_name:
                    author.name = author_name
            if commit_ts >= recent_cutoff:
                entry.recent_commits += 1
                entry.recent_lines += added + removed
            if entry.last_commit is None or commit_ts > entry.last_commit:
                entry.last_commit = commit_ts
                entry.last_author = author_name or "unknown"
            if entry.first_commit is None or commit_ts < entry.first_commit:
                entry.first_commit = commit_ts
            bucket = _activity_bucket(commit_ts, now)
            if bucket is not None:
                entry.activity[bucket] += 1
            file_activity_seen.add(path)

    return history
