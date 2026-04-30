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
