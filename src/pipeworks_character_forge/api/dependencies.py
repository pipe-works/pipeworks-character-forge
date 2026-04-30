"""FastAPI dependency providers for the runtime FLUX.2-klein manager.

The manager is constructed once at app startup and stored on
``app.state.manager``. Tests override :func:`get_manager` to inject a fake
that does not require the ``[ml]`` extra.
"""

from __future__ import annotations

from fastapi import Request

from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager


def get_manager(request: Request) -> Flux2KleinManager:
    """Return the per-app FLUX.2-klein manager instance."""
    manager: Flux2KleinManager = request.app.state.manager
    return manager
