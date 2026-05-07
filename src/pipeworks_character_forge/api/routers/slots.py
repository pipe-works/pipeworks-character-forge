"""POST /api/runs/{run_id}/slots/{slot_id}/regenerate.

Re-runs a single slot. Optional ``prompt`` body persists a new prompt
on the slot before queuing the job; subsequent regens of the same slot
keep that override unless explicitly changed.

Optional ``anchor_variant`` / ``scene`` bodies update the slot's
picker-snapshot fields in lock-step with the prompt, so the manifest
keeps telling the truth about which dropdown drove the current image.
Without these, repeated dropdown changes drift away from the recorded
``variant_pack`` / ``scene_pack`` and a page refresh ends up showing a
dropdown that lies about what was generated.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pipeworks_character_forge.api.dependencies import get_job_queue, get_orchestrator
from pipeworks_character_forge.api.services import anchor_variant, scene_pack
from pipeworks_character_forge.api.services.job_queue import JobQueue
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.api.services.run_store import RunManifest, scene_slot_id
from pipeworks_character_forge.api.services.scene_pack import SCENE_SLOT_INDICES
from pipeworks_character_forge.core.config import config

router = APIRouter()


class AnchorVariantPick(BaseModel):
    pack: str
    variant_id: str


class ScenePick(BaseModel):
    pack: str
    scene_id: str


class RegenerateRequest(BaseModel):
    prompt: str | None = None
    # Optional dropdown snapshot for anchor slots. When set on a
    # non-anchor (scene) slot the request is rejected — the metadata
    # would never be read back and silently storing it would mislead.
    anchor_variant: AnchorVariantPick | None = None
    # Optional dropdown snapshot for scene slots. Same shape rule:
    # rejected on anchor slots.
    scene: ScenePick | None = None


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


def _is_scene_slot(slot_id: str) -> bool:
    scene_ids = {scene_slot_id(i) for i in SCENE_SLOT_INDICES}
    return slot_id in scene_ids


def _apply_picker_snapshot(
    manifest: RunManifest,
    slot_id: str,
    request: RegenerateRequest,
) -> None:
    """Resolve and stamp picker metadata onto the slot.

    If ``request.prompt`` is None and a picker pick is supplied, the
    picker's prompt is also written to ``slot.prompt`` — that mirrors
    what the dropdown change would have filled the textarea with.
    Explicit ``request.prompt`` always wins, so an operator hand-edit
    is preserved while the dropdown snapshot still reflects which
    pack/variant the operator most recently selected.
    """
    slot = manifest.slots[slot_id]
    is_scene = _is_scene_slot(slot_id)

    if request.scene is not None and not is_scene:
        raise HTTPException(
            status_code=400,
            detail=f"`scene` is only valid for scene slots; {slot_id!r} is an anchor.",
        )
    if request.anchor_variant is not None and is_scene:
        raise HTTPException(
            status_code=400,
            detail=(
                f"`anchor_variant` is only valid for anchor slots; " f"{slot_id!r} is a scene slot."
            ),
        )

    if request.scene is not None:
        scene_packs = scene_pack.load(config.packs_dir).packs
        try:
            scene = scene_pack.resolve_scene(
                scene_packs, request.scene.pack, request.scene.scene_id
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        slot.scene_pack = request.scene.pack
        slot.scene_id = scene.id
        slot.scene_label = scene.label
        if request.prompt is None:
            slot.prompt = scene.default_prompt

    if request.anchor_variant is not None:
        variant_packs = anchor_variant.load(config.packs_dir).packs
        try:
            variant = anchor_variant.resolve_variant(
                variant_packs,
                request.anchor_variant.pack,
                slot_id,
                request.anchor_variant.variant_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        slot.variant_pack = request.anchor_variant.pack
        slot.variant_id = variant.id
        if request.prompt is None:
            slot.prompt = variant.prompt


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

    # Order matters: stamp the picker snapshot first so the picker's
    # default prompt (if any) is in place, then let an explicit
    # `prompt` override it. The picker resolver may itself raise 400
    # for unknown packs / picker-on-wrong-slot-type.
    _apply_picker_snapshot(manifest, slot_id, body)
    if body.prompt is not None:
        manifest.slots[slot_id].prompt = body.prompt
    if body.prompt is not None or body.anchor_variant is not None or body.scene is not None:
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
