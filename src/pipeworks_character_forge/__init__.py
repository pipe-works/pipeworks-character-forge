"""PipeWorks Character Forge — 25-image character dataset generator.

Local-only web app that turns one source image into a 25-image dataset
suitable for LoRA training, by chaining image-to-image runs through
``black-forest-labs/FLUX.2-klein-base-9B``.

Layers
------
core
    Configuration (:class:`PipeworksForgeConfig`) and the FLUX.2-klein
    pipeline lifecycle (added in PR 2).
api
    FastAPI application: slot catalog endpoint, source-image upload,
    run + per-slot regenerate endpoints (added in PR 3), SSE progress.
data
    Canonical 25-slot definition (``data/slots.json``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("pipeworks-character-forge")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
