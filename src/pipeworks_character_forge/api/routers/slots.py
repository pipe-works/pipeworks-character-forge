"""POST /api/runs/{run_id}/slots/{slot_id}/regenerate.

Re-runs a single slot. Optional ``prompt`` body persists a new prompt
on the slot before queuing the job; subsequent regens of the same slot
keep that override unless explicitly changed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pipeworks_character_forge.api.dependencies import get_job_queue, get_orchestrator
from pipeworks_character_forge.api.services.job_queue import JobQueue
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)

router = APIRouter()


class RegenerateRequest(BaseModel):
    prompt: str | None = None


class RegenerateResponse(BaseModel):
    run_id: str
    slot_id: str
    status: str
    queue_depth: int


class SlotPatchRequest(BaseModel):
    excluded: bool | None = None
    prompt: str | None = None


class SlotPatchResponse(BaseModel):
    run_id: str
    slot_id: str
    excluded: bool
    prompt: str


@router.post(
    "/api/runs/{run_id}/slots/{slot_id}/regenerate",
    response_model=RegenerateResponse,
    status_code=202,
)
def regenerate(
    run_id: str,
    slot_id: str,
    body: RegenerateRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> RegenerateResponse:
    if not orchestrator.run_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")

    manifest = orchestrator.run_store.load(run_id)
    if slot_id not in manifest.slots:
        raise HTTPException(status_code=404, detail=f"Unknown slot_id: {slot_id}")

    if body.prompt is not None:
        manifest.slots[slot_id].prompt = body.prompt
        orchestrator.run_store.save(manifest)

    job_queue.enqueue_regenerate(run_id, slot_id)

    return RegenerateResponse(
        run_id=run_id,
        slot_id=slot_id,
        status="queued",
        queue_depth=job_queue.depth(),
    )


@router.patch(
    "/api/runs/{run_id}/slots/{slot_id}",
    response_model=SlotPatchResponse,
)
def patch_slot(
    run_id: str,
    slot_id: str,
    body: SlotPatchRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_orchestrator)],
) -> SlotPatchResponse:
    """Update a slot's metadata without re-generating it.

    Currently exposes ``excluded`` (operator dataset curation) and
    ``prompt`` (override for the next regenerate). Both fields are
    optional — pass only the ones you want to change.
    """
    if not orchestrator.run_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")

    manifest = orchestrator.run_store.load(run_id)
    if slot_id not in manifest.slots:
        raise HTTPException(status_code=404, detail=f"Unknown slot_id: {slot_id}")

    slot_state = manifest.slots[slot_id]
    if body.excluded is not None:
        slot_state.excluded = body.excluded
    if body.prompt is not None:
        slot_state.prompt = body.prompt
    orchestrator.run_store.save(manifest)

    return SlotPatchResponse(
        run_id=run_id,
        slot_id=slot_id,
        excluded=slot_state.excluded,
        prompt=slot_state.prompt,
    )
