"""Static report and JSON export."""

from __future__ import annotations

import json
from io import StringIO

from rich.console import Console

from rot.demo import demo_snapshot
from rot.report import export_json, print_report, snapshot_payload

NOW = 1_750_000_000.0


def test_snapshot_payload_has_stable_schema(demo):
    payload = snapshot_payload(demo, demo=True)
    assert payload["schema"] == "rot.snapshot.v1"
    assert payload["version"] == "0.1.0"
    assert payload["demo"] is True
    assert payload["generated_at"]
    assert payload["summary"]["name"] == "ledger-api"
    assert payload["summary"]["risk_index"] == demo.summary.risk_index
    assert payload["summary"]["bus_factor"] == 2
    assert payload["summary"]["coverage_mode"] == "report"
    assert len(payload["files"]) == len(demo.files)
    assert payload["files"][0]["risk"] >= payload["files"][-1]["risk"]
    assert payload["files"][0]["path"] == demo.sorted_files("risk")[0].path


def test_file_payload_includes_history_tests_and_factors(demo):
    payload = snapshot_payload(demo, demo=False)
    top = payload["files"][0]
    assert set(
        (
            "path",
            "language",
            "is_test",
            "risk",
            "grade",
            "loc",
            "sloc",
            "size",
            "complexity",
            "history",
            "tests",
            "staleness_score",
            "factors",
        )
    ) <= set(top)
    assert top["complexity"]["max"] >= 1
    assert top["history"]["commits"] >= 0
    assert top["history"]["authors"] == sorted(
        top["history"]["authors"], key=lambda author: author["commits"], reverse=True
    )
    assert top["factors"] == sorted(
        top["factors"], key=lambda factor: factor["severity"], reverse=True
    )
    assert top["tests"]["coverage"] is None or 0 <= top["tests"]["coverage"] <= 1


def test_export_json_is_parseable(demo):
    raw = export_json(demo, demo=True)
    assert raw.endswith("\n")
    payload = json.loads(raw)
    assert payload["schema"] == "rot.snapshot.v1"
    assert payload["demo"] is True


def test_print_report_renders_at_multiple_widths(demo):
    for width in (70, 80, 100, 120, 150):
        output = StringIO()
        console = Console(file=output, width=width, force_terminal=False)
        print_report(demo, console, demo=True, top=5)
        text = output.getvalue()
        assert "ROT INDEX" in text
        assert "TOP ROT RISKS" in text
        assert "lib/legacy/tax_calc.py" in text
        assert "84 ms" in text or "scanned" in text


def test_print_report_honors_filter_and_top(demo):
    output = StringIO()
    console = Console(file=output, width=150, force_terminal=False)
    print_report(demo, console, demo=True, top=50, filter_text="legacy")
    text = output.getvalue()
    assert "lib/legacy/tax_calc.py" in text
    assert "services/payments/ledger.py" not in text
    assert " 2 files in view" in text


def test_print_report_empty_filter(demo):
    output = StringIO()
    console = Console(file=output, width=120, force_terminal=False)
    print_report(demo, console, demo=True, filter_text="no-such-path")
    text = output.getvalue()
    assert "no supported source files matched" in text
    assert " 0 files in view" in text


def test_print_report_includes_scan_warnings():
    snapshot = demo_snapshot(now=NOW)
    snapshot.summary.warnings = ["history capped at 5,000 commits"]
    output = StringIO()
    console = Console(file=output, width=150, force_terminal=False)
    print_report(snapshot, console, demo=True, top=1)
    assert "NOTES" in output.getvalue()
    assert "history capped at 5,000 commits" in output.getvalue()
