"""Static analysis: language detection, complexity, nesting, test proximity."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import FileMetric

MAX_FILE_BYTES = 1_500_000

LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".lua": "lua",
    ".r": "r",
    ".sql": "sql",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".cljc": "clojure",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".zig": "zig",
    ".nim": "nim",
    ".pl": "perl",
    ".pm": "perl",
    ".groovy": "groovy",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".sol": "solidity",
}

LANGUAGE_LABELS: dict[str, str] = {
    "python": "PY",
    "javascript": "JS",
    "typescript": "TS",
    "go": "GO",
    "rust": "RS",
    "java": "JAVA",
    "kotlin": "KT",
    "c": "C",
    "cpp": "C++",
    "csharp": "C#",
    "ruby": "RB",
    "php": "PHP",
    "swift": "SWIFT",
    "scala": "SCALA",
    "shell": "SH",
    "fish": "FISH",
    "lua": "LUA",
    "r": "R",
    "sql": "SQL",
    "vue": "VUE",
    "svelte": "SVELTE",
    "dart": "DART",
    "elixir": "EX",
    "erlang": "ERL",
    "clojure": "CLJ",
    "haskell": "HS",
    "ocaml": "ML",
    "zig": "ZIG",
    "nim": "NIM",
    "perl": "PL",
    "groovy": "GRV",
    "fsharp": "F#",
    "solidity": "SOL",
    "other": "TXT",
}

IGNORED_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "third_party",
    "third-party",
    "bower_components",
    "dist",
    "build",
    "target",
    "out",
    "coverage",
    "htmlcov",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
}

IGNORED_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".map",
    "_pb2.py",
    "_pb2_grpc.py",
    ".generated.ts",
    ".gen.go",
)

_SLASH_COMMENT_LANGS = {
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "kotlin",
    "c",
    "cpp",
    "csharp",
    "php",
    "swift",
    "scala",
    "dart",
    "groovy",
    "fsharp",
    "solidity",
    "vue",
    "svelte",
}
_HASH_COMMENT_LANGS = {
    "python",
    "ruby",
    "shell",
    "fish",
    "r",
    "perl",
    "elixir",
    "nim",
}
_TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "testdata"}
_TEST_SUFFIXES = (
    "_test.py",
    "_tests.py",
    "_test.go",
    "_test.rs",
    "_test.rb",
    "_test.exs",
    "_spec.rb",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    "test.java",
    "tests.java",
    "spec.scala",
    "test.scala",
    "tests.cs",
    "test.cs",
    "test.kt",
    "test.swift",
    "test.php",
)


def language_for(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    lowered = name.lower()
    for suffix in IGNORED_SUFFIXES:
        if lowered.endswith(suffix):
            return None
    dot = name.rfind(".")
    if dot < 0:
        return None
    return LANGUAGES.get(name[dot:].lower())


def is_candidate(path: str) -> bool:
    parts = [part.lower() for part in path.split("/")]
    if any(part in IGNORED_PARTS for part in parts[:-1]):
        return False
    name = parts[-1]
    if name.endswith(IGNORED_SUFFIXES):
        return False
    return language_for(path) is not None


def language_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, language[:5].upper())


def is_test_path(path: str) -> bool:
    parts = [part.lower() for part in path.split("/")]
    if any(part in _TEST_PARTS for part in parts[:-1]):
        return True
    name = parts[-1]
    if name.startswith("test_") or name.startswith("spec_"):
        return True
    if name == "conftest.py":
        return True
    return any(name.endswith(suffix) for suffix in _TEST_SUFFIXES)


class _PyComplexity(ast.NodeVisitor):
    """Count decision points per function and at module level."""

    def __init__(self) -> None:
        self.module_complexity = 1
        self.function_complexities: list[tuple[str, int]] = []
        self.functions = 0
        self.classes = 0
        self._stack: list[list[str | int]] = []

    def _bump(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        if self._stack:
            self._stack[-1][1] = int(self._stack[-1][1]) + amount
        else:
            self.module_complexity += amount

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions += 1
        self._stack.append([node.name, 1])
        self.generic_visit(node)
        name, complexity = self._stack.pop()
        self.function_complexities.append((str(name), int(complexity)))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes += 1
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self._bump(len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._bump(len(node.ifs))
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._bump(max(0, len(node.cases) - 1))
        self.generic_visit(node)


def _py_nesting(tree: ast.AST) -> int:
    maximum = 0
    stack: list[tuple[ast.AST, int]] = [(tree, 0)]
    nested_types = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )
    while stack:
        node, depth = stack.pop()
        if isinstance(node, nested_types):
            depth += 1
            maximum = max(maximum, depth)
        for child in ast.iter_child_nodes(node):
            stack.append((child, depth))
    return maximum


def _python_metrics(metric: FileMetric, text: str) -> None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        metric.parse_error = True
        _generic_metrics(metric, text)
        return

    visitor = _PyComplexity()
    visitor.visit(tree)
    complexities = [complexity for _, complexity in visitor.function_complexities]
    metric.functions = visitor.functions
    metric.classes = visitor.classes
    metric.max_complexity = max(
        [visitor.module_complexity, *complexities], default=visitor.module_complexity
    )
    metric.total_complexity = visitor.module_complexity + sum(complexities)
    metric.max_depth = _py_nesting(tree)
    if visitor.function_complexities:
        name, complexity = max(visitor.function_complexities, key=lambda item: item[1])
        if complexity > 1:
            metric.hot_function = name


def _scrub_comments(text: str, language: str) -> str:
    if language in _SLASH_COMMENT_LANGS:
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
        text = re.sub(r"(?m)//.*$", " ", text)
    if language in _HASH_COMMENT_LANGS:
        text = re.sub(r"(?m)#.*$", " ", text)
    if language == "sql":
        text = re.sub(r"(?m)--.*$", " ", text)
    # Don't let keywords inside string literals become false complexity.
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    return text


def _sloc(text: str, language: str) -> int:
    if not text:
        return 0
    count = 0
    in_block = False
    slash_comments = language in _SLASH_COMMENT_LANGS
    hash_comments = language in _HASH_COMMENT_LANGS
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if slash_comments and stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block = True
            continue
        if slash_comments and stripped.startswith("//"):
            continue
        if hash_comments and stripped.startswith("#"):
            continue
        if language == "sql" and stripped.startswith("--"):
            continue
        count += 1
    return count


_DECISION_RE = re.compile(
    r"\b(?:if|for|while|case|catch|elif|when|match)\b|&&|\|\|"
)
_FUNCTION_RE = re.compile(
    r"\b(?:function|def|func|fn|fun|sub|proc|method)\b|=>"
)
_CLASS_RE = re.compile(r"\b(?:class|struct|trait|interface|enum|object|module)\b")


def _generic_metrics(metric: FileMetric, text: str) -> None:
    language = metric.language
    clean = _scrub_comments(text, language)
    decisions = len(_DECISION_RE.findall(clean))
    metric.total_complexity = 1 + decisions
    metric.max_complexity = metric.total_complexity
    metric.functions = len(_FUNCTION_RE.findall(clean))
    metric.classes = len(_CLASS_RE.findall(clean))
    metric.hot_function = ""

    max_depth = 0
    brace_depth = 0
    for line in clean.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        brace_depth += stripped.count("{") - stripped.count("}")
        brace_depth = max(0, brace_depth)
        max_depth = max(max_depth, brace_depth)
        leading_tabs = len(line) - len(line.lstrip("\t"))
        leading_spaces = len(line) - len(line.lstrip(" "))
        indent = leading_tabs + leading_spaces // 4
        max_depth = max(max_depth, indent)
    metric.max_depth = max_depth


def analyze_file(root: Path, path: str) -> FileMetric | None:
    """Analyze one source file.  Returns None for unreadable/binary blobs."""
    language = language_for(path)
    if language is None:
        return None
    full = root / path
    try:
        info = full.stat()
    except OSError:
        return None
    if not full.is_file() or info.st_size > MAX_FILE_BYTES:
        return None
    try:
        raw = full.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8_192]:
        return None
    text = raw.decode("utf-8", errors="replace")
    metric = FileMetric(
        path=path,
        language=language,
        size=len(raw),
        loc=len(text.splitlines()),
        sloc=_sloc(text, language),
        max_complexity=1,
        total_complexity=1,
    )
    if language == "python":
        _python_metrics(metric, text)
    else:
        _generic_metrics(metric, text)
    # A syntax-error fallback should not inherit Python function counts from
    # the generic scanner's keyword search.
    if metric.parse_error:
        metric.max_complexity = max(1, metric.max_complexity)
    return metric


def link_tests(files: list[FileMetric], root: Path) -> int:
    """Attach a conservative test-proximity signal to source files.

    This is *not* line coverage.  It counts test files that mention the
    source module stem, or that pair with it by filename.  Real coverage
    from coverage.xml/lcov will overwrite the display later.
    """
    sources = [file for file in files if not is_test_path(file.path)]
    tests = [file for file in files if is_test_path(file.path)]
    if not sources or not tests:
        return 0

    by_stem: dict[str, list[FileMetric]] = {}
    for source in sources:
        stem = source.filename.rsplit(".", 1)[0].lower()
        if len(stem) < 3 or stem == "__init__":
            continue
        by_stem.setdefault(stem, []).append(source)

    linked: dict[str, set[str]] = {source.path: set() for source in sources}
    token_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
    for test in tests:
        full = root / test.path
        try:
            if full.stat().st_size > 800_000:
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens = {token.lower() for token in token_re.findall(text)}
        test_name = test.filename.lower()
        for prefix in ("test_", "spec_"):
            if prefix in test_name:
                test_name = test_name.split(prefix, 1)[-1]
        test_name = test_name.split(".", 1)[0]
        if test_name:
            tokens.add(test_name)
        for token in tokens:
            for source in by_stem.get(token, ()):
                if source.path != test.path:
                    linked[source.path].add(test.path)

    for source in sources:
        hits = sorted(linked[source.path])
        source.test_hits = len(hits)
        source.test_files = hits[:8]
    return sum(1 for source in sources if source.test_hits)
