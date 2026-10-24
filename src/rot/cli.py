"""Command line entry point for rot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from . import __version__
from .demo import demo_snapshot
from .git_history import GitError
from .models import Snapshot
from .report import export_json, print_report
from .scan import scan_repository


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from error
    if number < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rot",
        description=(
            "Scan a git repository and score codebase entropy: complexity, churn, "
            "ownership, test signal, and code rot. Launch the interactive dashboard "
            "or print a static report."
        ),
        epilog=(
            "examples:\n"
            "  rot                     launch the dashboard for the current repository\n"
            "  rot ~/code/project      launch against another checkout\n"
            "  rot --demo              explore the deterministic demo repository\n"
            "  rot --once --top 40     print a static report\n"
            "  rot --json > rot.json   emit machine-readable scan data\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="repository path (default: current directory)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use the built-in demo repository instead of scanning",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="print a static report and exit instead of launching the dashboard",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON snapshot (implies --once)",
    )
    parser.add_argument(
        "--max-commits",
        type=_positive_int,
        default=5_000,
        metavar="N",
        help="cap history parsing at N commits (default: 5000)",
    )
    parser.add_argument(
        "--max-files",
        type=_positive_int,
        default=6_000,
        metavar="N",
        help="cap source files analyzed at N (default: 6000)",
    )
    parser.add_argument(
        "--top",
        type=_positive_int,
        default=20,
        metavar="N",
        help="rows in the static top-risk table (default: 20)",
    )
    parser.add_argument(
        "--filter",
        default="",
        metavar="TEXT",
        help="only show paths containing TEXT",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rot {__version__}",
    )
    return parser


def _load_snapshot(args: argparse.Namespace) -> tuple[Snapshot, bool]:
    if args.demo:
        return demo_snapshot(), True
    path = Path(args.path).expanduser()
    if not path.exists():
        raise GitError(f"path does not exist: {path}")
    return (
        scan_repository(
            path,
            max_commits=args.max_commits,
            max_files=args.max_files,
        ),
        False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    try:
        snapshot, demo = _load_snapshot(args)
    except GitError as error:
        console.print(f"[bold red]rot:[/bold red] {error}", highlight=False)
        console.print(
            "[dim]Pass a path inside a git checkout, or use[/dim] "
            "[bold]rot --demo[/bold] [dim]to explore the demo.[/dim]",
            highlight=False,
        )
        return 2
    except OSError as error:
        console.print(f"[bold red]rot:[/bold red] {error}", highlight=False)
        return 2

    if args.json:
        sys.stdout.write(export_json(snapshot, demo=demo))
        return 0

    if args.once or not sys.stdout.isatty():
        print_report(
            snapshot,
            console,
            demo=demo,
            top=args.top,
            filter_text=args.filter,
        )
        return 0

    # Import Textual only when the interactive dashboard is actually used, so
    # --once/--json remain usable without a terminal-capable environment.
    from .app import RotApp

    app = RotApp(
        snapshot,
        repo_path=snapshot.summary.root,
        demo=demo,
        max_commits=args.max_commits,
        max_files=args.max_files,
        initial_filter=args.filter,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
