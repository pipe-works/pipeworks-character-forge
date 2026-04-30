"""FastAPI application for the PipeWorks Character Forge.

PR 3 surface: catalog + health (PR 1), plus source-image upload and a
throwaway ``/api/debug/i2i`` endpoint for proving the FLUX.2-klein
pipeline on Luminal's GPU. The full 25-slot orchestrator lands in PR 4.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from pipeworks_character_forge import __version__
from pipeworks_character_forge.api.routers import debug as debug_router
from pipeworks_character_forge.api.routers import source as source_router
from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.core.config import config
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct the FLUX.2-klein manager on startup; release VRAM on shutdown.

    Construction is cheap — the model is not loaded here. The first call
    to :meth:`Flux2KleinManager.i2i` triggers the lazy load.
    """
    manager = Flux2KleinManager(config)
    app.state.manager = manager
    logger.info("Lifespan start: manager constructed (model load is lazy)")
    try:
        yield
    finally:
        manager.unload()
        logger.info("Lifespan end: manager unloaded")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PipeWorks Character Forge",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(config.static_dir)),
        name="static",
    )

    app.include_router(source_router.router)
    app.include_router(debug_router.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/slots")
    def slots() -> dict[str, object]:
        catalog = slot_catalog.load_catalog()
        return {
            "schema_version": catalog.schema_version,
            "source_prompt": catalog.source_prompt,
            "intermediate": catalog.intermediate.model_dump(),
            "slots": [s.model_dump() for s in slot_catalog.list_slots()],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_html = (config.templates_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(index_html)

    return app


app = create_app()


def main() -> None:
    """Console-script entry point used by the systemd unit."""
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    uvicorn.run(
        "pipeworks_character_forge.api.main:app",
        host=config.server_host,
        port=config.server_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
