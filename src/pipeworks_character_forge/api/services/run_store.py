"""Disk-backed registry of generation runs.

One run = one directory under ``config.runs_dir`` containing
``source.png``, ``manifest.json``, and the per-slot ``NN_<slot>.png`` +
``NN_<slot>.txt`` outputs as the chain progresses.

Manifest writes are atomic (write-to-tmp + ``os.replace``) so concurrent
readers — typically the frontend polling for progress while the worker
thread is mid-run — never see a half-written file.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from pipeworks_character_forge.api.services.slot_catalog import SlotCatalog

SlotStatus = Literal["pending", "running", "done", "failed"]
RunStatus = Literal["pending", "running", "done", "failed", "cancelled"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SlotState(BaseModel):
    """One row in the manifest's ``slots`` map."""

    prompt: str
    image: str | None = None
    caption: str | None = None
    status: SlotStatus = "pending"
    seed_used: int | None = None
    regen_count: int = 0
    error: str | None = None
    # If True, this slot is omitted from `pw-forge make-dataset` and the
    # POST /api/runs/{id}/dataset endpoint. Lets the operator curate
    # drifted leaves out of the LoRA training set without deleting them
    # from disk. The stylized_base intermediate is always excluded from
    # the dataset regardless of this flag.
    excluded: bool = False


class RunParams(BaseModel):
    """Run-wide generation parameters."""

    seed: int = 1234
    steps: int = 28
    guidance: float = 4.5


class RunManifest(BaseModel):
    """The full per-run manifest as persisted to ``manifest.json``."""

    schema_version: int = 1
    run_id: str
    source_image: str = "source.png"
    trigger_word: str | None = None
    # Optional style guard text prepended to every slot's prompt at
    # generation time (NOT to captions — the LoRA learns style from
    # the images, captions stay clean). Use to lock visual identity
    # across all 26 outputs against the model's tendency to drift on
    # photographically-described scenes (e.g. spooky castle, rainy
    # street).
    style_prefix: str | None = None
    params: RunParams = Field(default_factory=RunParams)
    status: RunStatus = "pending"
    # Best-effort cancellation flag. The HTTP cancel endpoint sets this
    # to True; the orchestrator checks it between slots and bails out if
    # set, marking the run `cancelled`. The currently-running i2i call
    # cannot be interrupted (~52 s on the 5090 with cpu_offload), so
    # cancellation is best-effort, not immediate.
    cancel_requested: bool = False
    error: str | None = None
    slots: dict[str, SlotState] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class RunStore:
    """Filesystem-backed CRUD for :class:`RunManifest`."""

    MANIFEST_FILENAME = "manifest.json"

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / self.MANIFEST_FILENAME

    def exists(self, run_id: str) -> bool:
        return self.manifest_path(run_id).is_file()

    def list_run_ids(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.runs_dir.iterdir()
            if entry.is_dir()
            and not entry.name.startswith("_")
            and (entry / self.MANIFEST_FILENAME).is_file()
        )

    def create(
        self,
        *,
        run_id: str,
        source_path: Path,
        trigger_word: str | None,
        params: RunParams,
        catalog: SlotCatalog,
        slot_overrides: dict[str, str] | None = None,
        style_prefix: str | None = None,
    ) -> RunManifest:
        """Initialise the on-disk run dir, copy the source, write the manifest.

        ``slot_overrides`` lets the caller substitute a custom prompt per
        slot. Anything unspecified falls back to the catalog default.
        """
        overrides = slot_overrides or {}
        rd = self.run_dir(run_id)
        rd.mkdir(parents=True, exist_ok=True)

        target_source = rd / "source.png"
        if source_path.resolve() != target_source.resolve():
            shutil.copy(source_path, target_source)

        slots: dict[str, SlotState] = {}
        slots[catalog.intermediate.id] = SlotState(
            prompt=overrides.get(catalog.intermediate.id) or catalog.intermediate.default_prompt,
        )
        for slot in sorted(catalog.slots, key=lambda s: s.order):
            slots[slot.id] = SlotState(
                prompt=overrides.get(slot.id) or slot.default_prompt,
            )

        now = _now_iso()
        manifest = RunManifest(
            run_id=run_id,
            trigger_word=trigger_word,
            style_prefix=style_prefix,
            params=params,
            slots=slots,
            created_at=now,
            updated_at=now,
        )
        self.save(manifest)
        return manifest

    def load(self, run_id: str) -> RunManifest:
        path = self.manifest_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"manifest not found for run_id={run_id!r}")
        manifest: RunManifest = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        return manifest

    def save(self, manifest: RunManifest) -> None:
        manifest.updated_at = _now_iso()
        path = self.manifest_path(manifest.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)
