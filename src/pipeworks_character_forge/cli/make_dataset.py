"""``pw-forge make-dataset`` — export an ai-toolkit-ready dataset folder.

Given the run id of a *completed* run, copies the 25 leaf
``NN_<slot>.png`` + ``NN_<slot>.txt`` pairs (everything except the
intermediate stylized base, the original source, and the manifest) into
``<run-dir>/dataset/``. Point ai-toolkit at that path and train.

The pure-Python heart is :func:`export_run_dataset` — used by the CLI
here and reused by the HTTP endpoint at ``POST /api/runs/{id}/dataset``
so behavior is identical between SSH and one-click flows.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pipeworks_character_forge.api.services.run_store import RunStore
from pipeworks_character_forge.core.config import config


class DatasetExportError(Exception):
    """Operator-facing failure with an HTTP-shaped status code."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message

    def __str__(self) -> str:
        return self.message


@dataclass
class DatasetExportResult:
    output_dir: Path
    pairs_copied: int
    skipped: list[str] = field(default_factory=list)
    trigger_word_missing: bool = False


def export_run_dataset(
    store: RunStore,
    *,
    run_id: str,
    output_dir: Path | None,
    force: bool,
) -> DatasetExportResult:
    """Copy the 25 leaf PNG+TXT pairs into the dataset folder.

    Raises :class:`DatasetExportError` with status:

    - 404 — unknown run id
    - 409 — run is not in status ``done``
    - 409 — output dir exists and ``force`` is False
    """
    if not store.exists(run_id):
        raise DatasetExportError(
            404,
            f"Unknown run_id {run_id!r}",
        )

    manifest = store.load(run_id)
    if manifest.status != "done":
        raise DatasetExportError(
            409,
            f"Run {run_id} is in status {manifest.status!r}; "
            "refusing to export an incomplete dataset.",
        )

    run_dir = store.run_dir(run_id)
    target: Path = output_dir or (run_dir / "dataset")

    if target.exists():
        if not force:
            raise DatasetExportError(
                409,
                f"{target} already exists; pass force=True to overwrite.",
            )
        shutil.rmtree(target)

    target.mkdir(parents=True)

    pairs_copied = 0
    skipped: list[str] = []
    for slot_id, slot_state in manifest.slots.items():
        if slot_id == "stylized_base":
            continue
        if not (slot_state.image and slot_state.caption):
            skipped.append(slot_id)
            continue

        src_image = run_dir / slot_state.image
        src_caption = run_dir / slot_state.caption
        if not src_image.is_file() or not src_caption.is_file():
            skipped.append(slot_id)
            continue

        shutil.copy(src_image, target / slot_state.image)
        shutil.copy(src_caption, target / slot_state.caption)
        pairs_copied += 1

    return DatasetExportResult(
        output_dir=target,
        pairs_copied=pairs_copied,
        skipped=sorted(skipped),
        trigger_word_missing=not manifest.trigger_word,
    )


def add_make_dataset_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "make-dataset",
        help="Build an ai-toolkit-ready dataset/ subdir from a completed run.",
    )
    parser.add_argument("run_id", help="The run id (e.g. 2026-04-30T17-55_50b75).")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Override the default <run-dir>/dataset output location.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite an existing dataset directory.",
    )


def run_make_dataset(args: argparse.Namespace) -> int:
    store = RunStore(config.runs_dir)

    try:
        result = export_run_dataset(
            store,
            run_id=args.run_id,
            output_dir=args.output_dir,
            force=args.force,
        )
    except DatasetExportError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        # Map back to the legacy CLI exit codes so existing scripts
        # (and the test suite) keep working.
        if exc.status == 404:
            return 1
        if "incomplete" in exc.message.lower() or "status" in exc.message.lower():
            return 2
        return 3

    if result.trigger_word_missing:
        print(
            "warning: trigger_word is not set on this run; captions will not "
            "carry a LoRA prefix. Edit the .txt files by hand or re-run the "
            "chain with a trigger word set.",
            file=sys.stderr,
        )

    print(f"Wrote {result.pairs_copied} image+caption pairs to {result.output_dir}")
    if result.skipped:
        print(
            f"Skipped {len(result.skipped)} slot(s) with missing files: "
            f"{', '.join(result.skipped)}",
            file=sys.stderr,
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw-forge make-dataset")
    add_make_dataset_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(argv)
    return run_make_dataset(args)
