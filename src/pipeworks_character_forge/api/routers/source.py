"""POST /api/source-image — multipart upload of the source character image.

Saved under ``<runs_dir>/_staging/<source_id>.png`` so that subsequent run
requests can reference it by id without the client re-uploading.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from pipeworks_character_forge.core import image_io
from pipeworks_character_forge.core.config import config

router = APIRouter()

_STAGING_SUBDIR = "_staging"
_MAX_BYTES = 25 * 1024 * 1024  # 25 MiB — matches nginx client_max_body_size


@router.post("/api/source-image")
async def upload_source_image(file: UploadFile) -> dict[str, object]:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(payload) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Source image exceeds 25 MiB")

    try:
        image = image_io.load_image_bytes(payload)
    except Exception as exc:
        raise HTTPException(status_code=415, detail="Unsupported image format") from exc

    source_id = image_io.make_source_id(payload)
    staging_dir = config.runs_dir / _STAGING_SUBDIR
    target = staging_dir / f"{source_id}.png"
    image_io.save_png(image, target)

    return {
        "source_id": source_id,
        "width": image.width,
        "height": image.height,
        "path": str(target),
    }
