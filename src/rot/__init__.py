"""rot — a codebase entropy and health inspector."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rot")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.1.0"

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
