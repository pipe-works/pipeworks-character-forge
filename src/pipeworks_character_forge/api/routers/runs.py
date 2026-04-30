"""POST /api/runs and GET /api/runs[/{run_id}].

Creating a run validates the source upload, materialises the run dir +
manifest, and enqueues a full-chain job. Generation runs in the
background; clients poll ``GET /api/runs/{run_id}`` for progress.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pipeworks_character_forge.api.dependencies import get_job_queue, get_orchestrator
from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.api.services.job_queue import JobQueue
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.api.services.run_store import RunParams
from pipeworks_character_forge.core.config import config

router = APIRouter()


class CreateRunRequest(BaseModel):
    """Body for ``POST /api/runs``."""

    source_id: str
    trigger_word: str | None = None
    style_prefix: str | None = None
    seed: int = 1234
    steps: int = Field(default=28, ge=1, le=200)
    guidance: float = Field(default=4.5, ge=0.0, le=20.0)
    slot_overrides: dict[str, str] = Field(default_factory=dict)
    # If set, the orchestrator only generates these leaf slots. The
    # stylized base always runs (every leaf uses it as conditioning).
    # None means "run the full 25-leaf chain".
    only_slots: list[str] | None = None


class CreateRunResponse(BaseModel):
    run_id: str
    status: str
    queue_depth: int


class DatasetExportResponse(BaseModel):
    run_id: str
    path: str
    pairs: int
    skipped: list[str]
    excluded: list[str]


def _make_run_id() -> str:
    now = datetime.now(UTC)
    minute = now.strftime("%Y-%m-%dT%H-%M")
    digest = hashlib.sha256(now.isoformat().encode("utf-8")).hexdigest()[:5]
    return f"{minute}_{digest}"


@router.post("/api/runs", response_model=CreateRunResponse, status_code=201)
def create_run(
    body: CreateRunRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> CreateRunResponse:
    source_path = config.runs_dir / "_staging" / f"{body.source_id}.png"
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown source_id: {body.source_id}")

    catalog = slot_catalog.load_catalog()
    known_slot_ids = {catalog.intermediate.id} | {s.id for s in catalog.slots}
    unknown = set(body.slot_overrides) - known_slot_ids
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"slot_overrides references unknown slot ids: {sorted(unknown)}",
        )

    only_slots = body.only_slots
    if only_slots is not None:
        # Leaf-only filter — stylized_base is implicit and always runs.
        leaf_ids = {s.id for s in catalog.slots}
        only_slots = [s for s in only_slots if s != catalog.intermediate.id]
        unknown_only = set(only_slots) - leaf_ids
        if unknown_only:
            raise HTTPException(
                status_code=400,
                detail=f"only_slots references unknown slot ids: {sorted(unknown_only)}",
            )

    run_id = _make_run_id()
    orchestrator.run_store.create(
        run_id=run_id,
        source_path=source_path,
        trigger_word=body.trigger_word,
        style_prefix=body.style_prefix,
        params=RunParams(seed=body.seed, steps=body.steps, guidance=body.guidance),
        catalog=catalog,
        slot_overrides=body.slot_overrides,
        only_slots=only_slots,
    )
    job_queue.enqueue_full_run(run_id)

    return CreateRunResponse(
        run_id=run_id,
        status="queued",
        queue_depth=job_queue.depth(),
    )


@router.get("/api/runs")
def list_runs(
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
) -> dict[str, list[str]]:
    return {"run_ids": orchestrator.run_store.list_run_ids()}


@router.post("/api/runs/{run_id}/cascade", status_code=202)
def cascade_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> dict[str, object]:
    """Re-run stylized base + all 25 leaves on an existing run.

    Used when the operator wants the new base to propagate to every
    leaf without losing per-slot prompt edits or `excluded` flags
    (which the run-creation endpoint would reset). Returns 404 unknown
    run / 409 if the run is currently `running`.
    """
    if not orchestrator.run_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")
    manifest = orchestrator.run_store.load(run_id)
    if manifest.status == "running":
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is already running; cancel it first.",
        )

    job_queue.enqueue_cascade(run_id)
    return {
        "run_id": run_id,
        "status": "queued",
        "queue_depth": job_queue.depth(),
    }


@router.post("/api/runs/{run_id}/cancel", status_code=202)
def cancel_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
) -> dict[str, str]:
    """Best-effort cancellation.

    Flips the cancel flag on the manifest. The orchestrator checks it
    between slots; the currently-running i2i call (~52 s on the 5090)
    cannot be interrupted and finishes naturally. Returns 409 if the
    run is not currently in `running` state — there is nothing to
    cancel for `done` / `failed` / already-`cancelled` runs.
    """
    if not orchestrator.run_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")

    manifest = orchestrator.run_store.load(run_id)
    if manifest.status != "running":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot cancel run {run_id}: status is {manifest.status!r}; "
                "only 'running' runs can be cancelled."
            ),
        )

    manifest.cancel_requested = True
    orchestrator.run_store.save(manifest)
    return {"run_id": run_id, "status": "cancel_requested"}


@router.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    if not orchestrator.run_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")
    manifest = orchestrator.run_store.load(run_id)
    payload: dict[str, object] = manifest.model_dump()
    return payload


@router.post(
    "/api/runs/{run_id}/dataset",
    response_model=DatasetExportResponse,
    status_code=201,
)
def export_dataset(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
) -> DatasetExportResponse:
    """HTTP wrapper around ``pw-forge make-dataset``.

    Same logic, exposed so the frontend can offer a one-click
    "Create dataset" button. Always overwrites any existing
    ``dataset/`` subdir for the run.
    """
    # Local import — keeps the heavy CLI module out of the main API
    # surface's import graph for cold-start latency.
    from pipeworks_character_forge.cli.make_dataset import (
        DatasetExportError,
        export_run_dataset,
    )

    try:
        result = export_run_dataset(
            orchestrator.run_store,
            run_id=run_id,
            output_dir=None,
            force=True,
        )
    except DatasetExportError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    return DatasetExportResponse(
        run_id=run_id,
        path=str(result.output_dir),
        pairs=result.pairs_copied,
        skipped=result.skipped,
        excluded=result.excluded,
    )
