"""Entry point for the claude-sync CLI.

This wrapper exists so the console_scripts entry point resolves correctly
regardless of the working directory when the exe is invoked.
"""
import sys
import os

# Ensure the package root is on sys.path so `src.*` imports work
# from any working directory (e.g. when invoked by a VSCode extension)
_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from src.cli import cli  # noqa: E402


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
