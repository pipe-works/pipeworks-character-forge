"""FastAPI dependency providers for app-state singletons.

The manager, orchestrator, and job queue are constructed once at app
startup (see :func:`api.main.lifespan`) and stashed on
``app.state``. Tests override the corresponding ``get_*`` functions to
inject fakes that don't need torch / diffusers / a GPU.
"""

from __future__ import annotations

from fastapi import Request

from pipeworks_character_forge.api.services.job_queue import JobQueue
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager


def get_manager(request: Request) -> Flux2KleinManager:
    """Return the per-app FLUX.2-klein manager instance."""
    manager: Flux2KleinManager = request.app.state.manager
    return manager


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    orchestrator: PipelineOrchestrator = request.app.state.orchestrator
    return orchestrator


def get_job_queue(request: Request) -> JobQueue:
    job_queue: JobQueue = request.app.state.job_queue
    return job_queue
