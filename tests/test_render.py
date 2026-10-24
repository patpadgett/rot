"""Rich renderers for the dossier, inspection modal, and help."""

from __future__ import annotations

from rot.demo import demo_snapshot
from rot.render import dossier_text, help_text, inspect_text

NOW = 1_750_000_000.0


def test_dossier_text_includes_core_sections():
    snapshot = demo_snapshot(now=NOW)
    file = snapshot.sorted_files("risk")[0]
    text = dossier_text(file, snapshot.now).plain
    assert file.path in text
    assert "RISK" in text
    assert "COMPLEXITY" in text
    assert "CHURN" in text
    assert "LAST CHANGE" in text
    assert "OWNERSHIP" in text
    assert "TESTS" in text
    assert "ROT SIGNALS" in text
    assert "BLAST RADIUS" in text
    assert "enter for full dossier" in text


def test_dossier_text_handles_a_test_file_without_penalty():
    snapshot = demo_snapshot(now=NOW)
    file = next(file for file in snapshot.files if file.is_test)
    text = dossier_text(file, snapshot.now).plain
    assert "TEST" in text
    assert "test file" in text
    assert "coverage penalties off" in text


def test_inspect_text_has_structure_history_and_first_moves():
    snapshot = demo_snapshot(now=NOW)
    file = next(file for file in snapshot.sorted_files("risk") if not file.is_test)
    text = inspect_text(file, snapshot.summary, snapshot.now).plain
    assert "FILE DOSSIER" in text
    assert file.path in text
    assert "STRUCTURE" in text
    assert "HISTORY" in text
    assert "TEST SIGNAL" in text
    assert "ROT SIGNALS" in text
    assert "BLAST RADIUS" in text
    assert "COMMIT PULSE" in text
    assert "FIRST MOVES" in text
    assert "never runs your tests" in text


def test_help_text_documents_keys_and_scoring():
    text = help_text().plain
    for phrase in (
        "codebase entropy",
        "move through the file leaderboard",
        "filter paths",
        "cycle sort",
        "recolor the entropy map",
        "g / G",
        "rescan the working tree",
        "HOW THE ROT INDEX WORKS",
        "COVERAGE, HONESTLY",
        "ENTROPY MAP",
    ):
        assert phrase in text
