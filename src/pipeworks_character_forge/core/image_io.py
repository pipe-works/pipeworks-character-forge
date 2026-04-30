"""Image-IO helpers shared by the source-image upload and the orchestrator."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image


def normalize_rgb(image: Image.Image) -> Image.Image:
    """Return an RGB copy of an arbitrary-mode PIL image."""
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def make_source_id(payload: bytes) -> str:
    """Stable id for an uploaded source image.

    Format: ``<utc-iso-min>_<5-char-hash>`` where the hash is the first 5 hex
    chars of ``sha256(payload + utc-iso-second-bytes)``. Filesystem-safe,
    sortable, and unique enough in practice for a single-user app.
    """
    now = datetime.now(UTC)
    minute = now.strftime("%Y-%m-%dT%H-%M")
    second = now.strftime("%Y-%m-%dT%H-%M-%S").encode("utf-8")
    digest = hashlib.sha256(payload + second).hexdigest()[:5]
    return f"{minute}_{digest}"


def save_png(image: Image.Image, path: Path) -> None:
    """Write a PIL image to *path* as PNG, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def load_image_bytes(payload: bytes) -> Image.Image:
    """Load an image from raw bytes and normalize to RGB."""
    image = Image.open(BytesIO(payload))
    return normalize_rgb(image)
