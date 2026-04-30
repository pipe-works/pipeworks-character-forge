"""POST /api/debug/i2i — throwaway endpoint to prove FLUX.2-klein works.

Accepts a previously-uploaded ``source_id`` plus prompt and generation
parameters; returns one PNG. Used in PR 3 to measure VRAM and validate
the pipeline on Luminal's GPU before the full 25-slot orchestrator
lands. Not part of the user-facing UI.
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response
from PIL import Image

from pipeworks_character_forge.api.dependencies import get_manager
from pipeworks_character_forge.core.config import config
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager

router = APIRouter()


@router.post("/api/debug/i2i")
def debug_i2i(
    source_id: Annotated[str, Form()],
    prompt: Annotated[str, Form()],
    manager: Annotated[Flux2KleinManager, Depends(get_manager)],
    steps: Annotated[int, Form()] = 28,
    guidance: Annotated[float, Form()] = 4.5,
    strength: Annotated[float, Form()] = 0.6,
    seed: Annotated[int, Form()] = 1234,
) -> Response:
    source_path = config.runs_dir / "_staging" / f"{source_id}.png"
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown source_id: {source_id}")

    reference = Image.open(source_path).convert("RGB")
    output = manager.i2i(
        reference,
        prompt,
        steps=steps,
        guidance=guidance,
        strength=strength,
        seed=seed,
    )

    buffer = BytesIO()
    output.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")
