"""``pw-forge make-dataset`` — export an ai-toolkit-ready dataset folder.

Given the run id of a *completed* run, copies the 25 leaf
``NN_<slot>.png`` + ``NN_<slot>.txt`` pairs (everything except the
intermediate stylized base, the original source, and the manifest) into
``<run-dir>/dataset/``. Point ai-toolkit at that path and train.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from pipeworks_character_forge.api.services.run_store import RunStore
from pipeworks_character_forge.core.config import config


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

    if not store.exists(args.run_id):
        print(f"error: unknown run_id {args.run_id!r}", file=sys.stderr)
        print(f"       (looked under {config.runs_dir})", file=sys.stderr)
        return 1

    manifest = store.load(args.run_id)
    if manifest.status != "done":
        print(
            f"error: run {args.run_id} is in status {manifest.status!r}; "
            "refusing to export an incomplete dataset.",
            file=sys.stderr,
        )
        return 2

    run_dir = store.run_dir(args.run_id)
    output_dir: Path = args.output_dir or (run_dir / "dataset")

    if output_dir.exists():
        if not args.force:
            print(
                f"error: {output_dir} already exists; pass --force to overwrite.",
                file=sys.stderr,
            )
            return 3
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True)

    if not manifest.trigger_word:
        print(
            "warning: trigger_word is not set on this run; captions will not "
            "carry a LoRA prefix. Edit the .txt files by hand or re-run the "
            "chain with a trigger word set.",
            file=sys.stderr,
        )

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

        shutil.copy(src_image, output_dir / slot_state.image)
        shutil.copy(src_caption, output_dir / slot_state.caption)
        pairs_copied += 1

    print(f"Wrote {pairs_copied} image+caption pairs to {output_dir}")
    if skipped:
        print(
            f"Skipped {len(skipped)} slot(s) with missing files: "
            f"{', '.join(sorted(skipped))}",
            file=sys.stderr,
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw-forge make-dataset")
    add_make_dataset_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(argv)
    return run_make_dataset(args)
