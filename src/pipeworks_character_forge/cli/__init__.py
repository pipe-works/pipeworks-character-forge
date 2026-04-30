"""Console-script entry point for the ``pw-forge`` command.

Two subcommands today:

- ``pw-forge serve`` — run the FastAPI server (default if no subcommand
  is given, so the existing systemd unit's ``ExecStart=pw-forge`` keeps
  working unchanged).
- ``pw-forge make-dataset <run_id>`` — copy the 25 leaf PNG+TXT pairs
  from a completed run into ``<run-dir>/dataset/`` so ai-toolkit can
  point at it directly.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pipeworks_character_forge.cli.make_dataset import (
    add_make_dataset_parser,
    run_make_dataset,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pw-forge")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the FastAPI server (default).")
    add_make_dataset_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "make-dataset":
        return run_make_dataset(args)

    # Default: serve. Imported lazily so the CLI's ``make-dataset`` path
    # does not pull in uvicorn / FastAPI startup machinery.
    from pipeworks_character_forge.api.main import main as serve_main

    serve_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
