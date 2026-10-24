"""Coverage readers accept the common reports without running tests."""

from __future__ import annotations

import json
from pathlib import Path

from rot.coverage_data import coverage_db_is_readable, load_coverage


def test_reads_coverage_xml(tmp_path: Path):
    (tmp_path / "coverage.xml").write_text(
        """<?xml version="1.0" ?>
<coverage>
  <packages><package><classes>
    <class filename="service/app.py" line-rate="0.75">
      <lines>
        <line number="1" hits="1"/>
        <line number="2" hits="1"/>
        <line number="3" hits="0"/>
        <line number="4" hits="1"/>
      </lines>
    </class>
    <class filename="./service/util.py" line-rate="0.5"/>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )
    report, source = load_coverage(tmp_path)
    assert source == "coverage.xml"
    assert report["service/app.py"] == (0.75, "coverage.xml")
    assert report["service/util.py"] == (0.5, "coverage.xml")


def test_reads_coverage_json_and_ignores_parent_paths(tmp_path: Path):
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "service/app.py": {"summary": {"percent_covered": 82.5}},
                    "service/util.py": {
                        "executed_lines": [1, 2, 3],
                        "missing_lines": [4],
                    },
                    "../outside.py": {"summary": {"percent_covered": 10}},
                }
            }
        ),
        encoding="utf-8",
    )
    report, source = load_coverage(tmp_path)
    assert source == "coverage.json"
    assert report["service/app.py"] == (0.825, "coverage.json")
    assert report["service/util.py"] == (0.75, "coverage.json")
    assert "../outside.py" not in report


def test_reads_lcov_with_lf_lh_and_da_fallbacks(tmp_path: Path):
    (tmp_path / "lcov.info").write_text(
        "SF:service/app.py\n"
        "LF:10\n"
        "LH:8\n"
        "end_of_record\n"
        "SF:service/util.py\n"
        "DA:1,1\n"
        "DA:2,0\n"
        "DA:3,4\n"
        "end_of_record\n",
        encoding="utf-8",
    )
    report, source = load_coverage(tmp_path)
    assert source == "lcov.info"
    assert report["service/app.py"] == (0.8, "lcov.info")
    assert report["service/util.py"] == (2 / 3, "lcov.info")


def test_first_nonempty_report_wins(tmp_path: Path):
    (tmp_path / "coverage.xml").write_text("<coverage/>", encoding="utf-8")
    (tmp_path / "coverage.json").write_text(
        json.dumps({"files": {"app.py": {"summary": {"percent_covered": 50}}}}),
        encoding="utf-8",
    )
    report, source = load_coverage(tmp_path)
    assert source == "coverage.json"
    assert report["app.py"] == (0.5, "coverage.json")


def test_missing_or_broken_reports_are_silent(tmp_path: Path):
    assert load_coverage(tmp_path) == ({}, None)
    (tmp_path / "coverage.xml").write_text("not xml", encoding="utf-8")
    (tmp_path / "coverage.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "lcov.info").write_text("SF:empty.py\nend_of_record\n", encoding="utf-8")
    assert load_coverage(tmp_path) == ({}, None)
    assert coverage_db_is_readable(tmp_path / "missing.coverage") is False
