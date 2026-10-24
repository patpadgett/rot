"""Shared fixtures: a deterministic demo snapshot and a small git repo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from rot.demo import demo_snapshot

# A fixed clock keeps age-based scores stable in assertions.
NOW = 1_750_000_000.0
DAY = 86_400.0


def run_git(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    base_env = os.environ.copy()
    base_env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Ada Lovelace",
            "GIT_AUTHOR_EMAIL": "ada@example.com",
            "GIT_COMMITTER_NAME": "Ada Lovelace",
            "GIT_COMMITTER_EMAIL": "ada@example.com",
        }
    )
    if env:
        base_env.update(env)
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=base_env,
    )


class RepoBuilder:
    """Tiny helper for constructing a repo with fixed commit timestamps."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "user.name", "Ada Lovelace")
        run_git(self.root, "config", "user.email", "ada@example.com")
        run_git(self.root, "config", "commit.gpgsign", "false")

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(
        self,
        message: str,
        *,
        timestamp: float,
        author: tuple[str, str] | None = None,
    ) -> None:
        run_git(self.root, "add", "-A")
        date = f"@{int(timestamp)} +0000"
        env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        if author is not None:
            name, email = author
            env.update(
                {
                    "GIT_AUTHOR_NAME": name,
                    "GIT_AUTHOR_EMAIL": email,
                    "GIT_COMMITTER_NAME": name,
                    "GIT_COMMITTER_EMAIL": email,
                }
            )
        run_git(self.root, "commit", "-q", "-m", message, env=env)
        # Reset the identity for subsequent commits unless overridden again.
        run_git(self.root, "config", "user.name", "Ada Lovelace")
        run_git(self.root, "config", "user.email", "ada@example.com")


@pytest.fixture
def demo():
    return demo_snapshot(now=NOW)


@pytest.fixture
def repo(tmp_path: Path) -> RepoBuilder:
    """A small repo with two authors, three commits, and a stale file."""
    builder = RepoBuilder(tmp_path / "sample")
    builder.write(
        "service/app.py",
        "def handle(value):\n"
        "    if value:\n"
        "        return value * 2\n"
        "    return 0\n",
    )
    builder.write(
        "service/util.py",
        "def add(left, right):\n    return left + right\n",
    )
    builder.write(
        "legacy/currency.py",
        "def convert(amount, rate):\n"
        "    if rate <= 0:\n"
        "        return 0\n"
        "    return amount * rate\n",
    )
    builder.write("tests/test_app.py", "from service.app import handle\n")
    builder.commit("initial service", timestamp=NOW - 400 * DAY)

    builder.write(
        "service/app.py",
        "def handle(value, limit=10):\n"
        "    if value > limit:\n"
        "        value = limit\n"
        "    for index in range(value):\n"
        "        if index % 2:\n"
        "            value += index\n"
        "    return value\n",
    )
    builder.write(
        "web/view.ts",
        "export function view(items: string[]) {\n"
        "  if (!items.length) {\n"
        "    return '';\n"
        "  }\n"
        "  return items.join(',');\n"
        "}\n",
    )
    builder.commit(
        "tighten app and add view",
        timestamp=NOW - 30 * DAY,
        author=("Grace Hopper", "grace@example.com"),
    )

    builder.write(
        "service/util.py",
        "def add(left, right):\n"
        "    if left is None or right is None:\n"
        "        return 0\n"
        "    return left + right\n",
    )
    builder.commit("guard util", timestamp=NOW - 10 * DAY)
    return builder
