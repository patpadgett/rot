"""Static analysis, test detection, and the test-link heuristic."""

from __future__ import annotations

from pathlib import Path

from rot.analyze import (
    analyze_file,
    is_candidate,
    is_test_path,
    language_for,
    language_label,
    link_tests,
)
from rot.models import FileMetric


def test_language_detection_and_ignored_paths():
    assert language_for("src/app.py") == "python"
    assert language_for("src/app.tsx") == "typescript"
    assert language_for("src/app.min.js") is None
    assert language_for("README.md") is None
    assert language_label("python") == "PY"
    assert language_label("solidity") == "SOL"

    assert is_candidate("src/app.py")
    assert not is_candidate("node_modules/pkg/index.js")
    assert not is_candidate("dist/bundle.js")
    assert not is_candidate("src/generated_pb2.py")


def test_test_path_detection():
    assert is_test_path("tests/test_app.py")
    assert is_test_path("src/app_test.go")
    assert is_test_path("src/App.test.tsx")
    assert is_test_path("src/spec_helper.rb")
    assert is_test_path("conftest.py")
    assert not is_test_path("src/app.py")
    assert not is_test_path("src/testing.py")


def test_python_complexity_and_nesting(tmp_path: Path):
    source = (
        "class Worker:\n"
        "    def choose(self, value):\n"
        "        if value:\n"
        "            for item in range(value):\n"
        "                if item % 2:\n"
        "                    return item\n"
        "        return 0\n"
    )
    (tmp_path / "worker.py").write_text(source, encoding="utf-8")
    metric = analyze_file(tmp_path, "worker.py")
    assert metric is not None
    assert metric.language == "python"
    assert metric.functions == 1
    assert metric.classes == 1
    assert metric.max_complexity == 4
    assert metric.total_complexity == 5
    assert metric.max_depth == 5
    assert metric.hot_function == "choose"
    assert metric.sloc == 7


def test_python_parse_error_falls_back_to_generic_metrics(tmp_path: Path):
    (tmp_path / "broken.py").write_text(
        "def broken(:\n    if x:\n        return 1\n", encoding="utf-8"
    )
    metric = analyze_file(tmp_path, "broken.py")
    assert metric is not None
    assert metric.parse_error is True
    assert metric.max_complexity >= 2
    assert metric.sloc == 3


def test_generic_language_metrics(tmp_path: Path):
    (tmp_path / "view.ts").write_text(
        "// a comment\n"
        "export function view(items: string[]) {\n"
        "  if (!items.length) {\n"
        "    return '';\n"
        "  }\n"
        "  for (const item of items) {\n"
        "    if (item) {\n"
        "      return item;\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    metric = analyze_file(tmp_path, "view.ts")
    assert metric is not None
    assert metric.language == "typescript"
    assert metric.functions >= 1
    assert metric.max_complexity >= 3
    assert metric.max_depth >= 1
    assert metric.sloc == 10


def test_analyze_file_rejects_binary_and_oversized(tmp_path: Path):
    (tmp_path / "blob.py").write_bytes(b"\x00\x01\x02")
    assert analyze_file(tmp_path, "blob.py") is None
    (tmp_path / "huge.py").write_bytes(b"x" * 1_600_000)
    assert analyze_file(tmp_path, "huge.py") is None
    assert analyze_file(tmp_path, "missing.py") is None


def test_link_tests_matches_stems_and_skips_tiny_stems(tmp_path: Path):
    root = tmp_path
    for relative in ("app.py", "payments.py", "db.py", "__init__.py"):
        (root / relative).write_text("value = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text(
        "from app import value\n", encoding="utf-8"
    )
    (root / "tests" / "test_payments.py").write_text(
        "import payments\n", encoding="utf-8"
    )
    files = [
        FileMetric(path=path, language="python", sloc=1)
        for path in ("app.py", "payments.py", "db.py", "__init__.py")
    ] + [
        FileMetric(path=path, language="python", sloc=1)
        for path in ("tests/test_app.py", "tests/test_payments.py")
    ]
    files[3].test_hits = 0
    linked = link_tests(files, root)

    by_path = {file.path: file for file in files}
    assert linked == 2
    assert by_path["app.py"].test_hits == 1
    assert by_path["app.py"].test_files == ["tests/test_app.py"]
    assert by_path["payments.py"].test_hits == 1
    # "db" is shorter than the three-character stem threshold.
    assert by_path["db.py"].test_hits == 0
    assert by_path["__init__.py"].test_hits == 0


def test_link_tests_without_tests_returns_zero(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    files = [FileMetric(path="app.py", language="python", sloc=1)]
    assert link_tests(files, tmp_path) == 0
    assert files[0].test_hits == 0
