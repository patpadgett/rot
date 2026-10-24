"""Read existing coverage artifacts without running the test suite."""

from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable


def _normalize(root: Path, raw: str) -> str | None:
    raw = raw.strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return None
    if raw.startswith("../"):
        return None
    return raw.lstrip("/")


def _load_xml(root: Path) -> dict[str, tuple[float, str]]:
    path = root / "coverage.xml"
    if not path.is_file():
        return {}
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError):
        return {}
    buckets: dict[str, list[float]] = {}
    line_hits: dict[str, dict[int, bool]] = {}
    for element in tree.getroot().iter("class"):
        filename = element.get("filename")
        if not filename:
            continue
        relative = _normalize(root, filename)
        if not relative:
            continue
        lines = element.find("lines")
        if lines is not None:
            bits = line_hits.setdefault(relative, {})
            for line in lines.findall("line"):
                try:
                    number = int(line.get("number", ""))
                    hits = int(line.get("hits", "0"))
                except ValueError:
                    continue
                bits[number] = bits.get(number, False) or hits > 0
        rate = element.get("line-rate")
        if rate is not None:
            try:
                buckets.setdefault(relative, []).append(float(rate))
            except ValueError:
                pass
    result: dict[str, tuple[float, str]] = {}
    for relative, bits in line_hits.items():
        if bits:
            result[relative] = (sum(bits.values()) / len(bits), "coverage.xml")
    for relative, rates in buckets.items():
        if relative not in result and rates:
            result[relative] = (sum(rates) / len(rates), "coverage.xml")
    return result


def _load_json(root: Path) -> dict[str, tuple[float, str]]:
    path = root / "coverage.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    files = data.get("files")
    if not isinstance(files, dict):
        return {}
    result: dict[str, tuple[float, str]] = {}
    for filename, entry in files.items():
        relative = _normalize(root, str(filename))
        if not relative or not isinstance(entry, dict):
            continue
        summary = entry.get("summary") or {}
        percent = summary.get("percent_covered")
        if isinstance(percent, (int, float)):
            result[relative] = (max(0.0, min(1.0, percent / 100.0)), "coverage.json")
            continue
        executed = entry.get("executed_lines") or []
        missing = entry.get("missing_lines") or []
        total = len(executed) + len(missing)
        if total:
            result[relative] = (len(executed) / total, "coverage.json")
    return result


def _load_lcov(root: Path) -> dict[str, tuple[float, str]]:
    path = root / "lcov.info"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    result: dict[str, tuple[float, str]] = {}
    current: str | None = None
    found = 0
    hit = 0
    da_total = 0
    da_hit = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("SF:"):
            current = _normalize(root, line[3:])
            found = hit = da_total = da_hit = 0
        elif line.startswith("LF:"):
            try:
                found = int(line[3:])
            except ValueError:
                found = 0
        elif line.startswith("LH:"):
            try:
                hit = int(line[3:])
            except ValueError:
                hit = 0
        elif line.startswith("DA:"):
            try:
                _, hits = line[3:].split(",", 1)
                da_total += 1
                da_hit += int(hits) > 0
            except ValueError:
                pass
        elif line == "end_of_record" and current:
            total = found or da_total
            covered = hit or da_hit
            if total:
                result[current] = (max(0.0, min(1.0, covered / total)), "lcov.info")
            current = None
    return result


def _load_coverage_db(root: Path) -> dict[str, tuple[float, str]]:
    """Use coverage.py's own parser when the optional package is available."""
    data_file = root / ".coverage"
    if not data_file.is_file():
        return {}
    try:
        import coverage  # type: ignore[import-not-found]
    except ImportError:
        return {}
    try:
        cov = coverage.Coverage(data_file=str(data_file))
        cov.load()
        measured = cov.get_data().measured_files()
    except Exception:
        return {}

    result: dict[str, tuple[float, str]] = {}
    for filename in measured:
        try:
            analysis = cov.analysis2(filename)
        except Exception:
            continue
        statements = set(analysis[1])
        missing = set(analysis[3])
        if not statements:
            continue
        ratio = (len(statements) - len(missing)) / len(statements)
        relative = _normalize(root, filename)
        if relative:
            result[relative] = (max(0.0, min(1.0, ratio)), ".coverage")
    return result


_LOADERS: tuple[tuple[str, Callable[[Path], dict[str, tuple[float, str]]]], ...] = (
    ("coverage.xml", _load_xml),
    ("coverage.json", _load_json),
    ("lcov.info", _load_lcov),
    (".coverage", _load_coverage_db),
)


def load_coverage(root: Path) -> tuple[dict[str, tuple[float, str]], str | None]:
    """Return {repo-relative path: (ratio, source)} from the first report found."""
    for label, loader in _LOADERS:
        report = loader(root)
        if report:
            return report, label
    return {}, None


def coverage_db_is_readable(path: Path) -> bool:
    """Small diagnostic used by tests and the scan warning path."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        finally:
            connection.close()
        return True
    except sqlite3.Error:
        return False
