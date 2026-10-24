"""CLI argument handling, JSON output, and the non-TTY fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rot.cli import build_parser, main


def test_parser_help_and_version(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as version:
        parser.parse_args(["--version"])
    assert version.value.code == 0
    assert "rot 0.1.0" in capsys.readouterr().out

    with pytest.raises(SystemExit) as help_exit:
        parser.parse_args(["--help"])
    assert help_exit.value.code == 0
    assert "usage: rot" in capsys.readouterr().out


def test_parser_rejects_nonpositive_limits():
    parser = build_parser()
    for flag in ("--max-commits", "--max-files", "--top"):
        with pytest.raises(SystemExit):
            parser.parse_args([flag, "0"])


def test_json_output_is_valid(capsys):
    assert main(["--demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "rot.snapshot.v1"
    assert payload["demo"] is True
    assert payload["summary"]["name"] == "ledger-api"
    assert payload["files"]


def test_once_report_prints(capsys):
    assert main(["--demo", "--once", "--top", "3"]) == 0
    output = capsys.readouterr().out
    assert "ROT INDEX" in output
    assert "TOP ROT RISKS" in output
    assert "lib/legacy/tax_calc.py" in output
    assert "COMMAND" not in output


def test_once_report_honors_filter(capsys):
    assert main(["--demo", "--once", "--filter", "legacy"]) == 0
    output = capsys.readouterr().out
    assert "lib/legacy/tax_calc.py" in output
    assert "services/payments/ledger.py" not in output
    assert "2 files in view" in output


def test_non_tty_falls_back_to_static_report(capsys):
    # capsys gives us a non-TTY stdout, which must never try to start Textual.
    assert main(["--demo"]) == 0
    output = capsys.readouterr().out
    assert "ROT INDEX" in output
    assert "TOP ROT RISKS" in output


def test_missing_path_returns_two(capsys, tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    assert main([str(missing)]) == 2
    error = capsys.readouterr().out
    assert "path does not exist" in error
    assert "rot --demo" in error


def test_non_repository_returns_two(capsys, tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert main([str(plain)]) == 2
    error = capsys.readouterr().out
    assert "not a git repository" in error


def test_json_error_still_returns_two(capsys, tmp_path: Path):
    missing = tmp_path / "nope"
    assert main([str(missing), "--json"]) == 2
    assert "path does not exist" in capsys.readouterr().out
