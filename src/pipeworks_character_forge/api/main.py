"""FastAPI application for the PipeWorks Character Forge.

PR 9 surface: catalog + health (PR 1), source upload + debug i2i
(PR 4), and the full-chain orchestrator behind ``POST /api/runs`` +
``POST /api/runs/{run_id}/slots/{slot_id}/regenerate`` + manifest
polling. The frontend lands in PR 10.
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
from pipeworks_character_forge.api.routers import runs as runs_router
from pipeworks_character_forge.api.routers import slots as slots_router
from pipeworks_character_forge.api.routers import source as source_router
from pipeworks_character_forge.api.services import anchor_variant, scene_pack, slot_catalog
from pipeworks_character_forge.api.services.job_queue import JobQueue
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.api.services.run_store import RunStore
from pipeworks_character_forge.core.config import config
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct the manager + orchestrator + job queue on startup."""
    # Runtime directories are created at startup, not at module import,
    # so unit tests can monkey-patch config.runs_dir to a tmp location
    # before any filesystem side-effect lands.
    config.runs_dir.mkdir(parents=True, exist_ok=True)
    # Seed bundled scene packs and anchor-variant packs into the runtime
    # dir on first deploy. Both are idempotent — operator edits stay
    # sticky across upgrades.
    scene_pack.bootstrap(config.packs_dir, config.data_dir / "scene_packs")
    anchor_variant.bootstrap(config.packs_dir, config.data_dir / "anchor_variants")

    manager = Flux2KleinManager(config)
    catalog = slot_catalog.load_catalog()
    run_store = RunStore(config.runs_dir)
    orchestrator = PipelineOrchestrator(manager=manager, run_store=run_store, catalog=catalog)
    job_queue = JobQueue(orchestrator)
    job_queue.start()

    app.state.manager = manager
    app.state.run_store = run_store
    app.state.orchestrator = orchestrator
    app.state.job_queue = job_queue

    logger.info("Lifespan start: manager constructed (lazy load); job queue worker running")
    try:
        yield
    finally:
        job_queue.stop()
        manager.unload()
        logger.info("Lifespan end: manager unloaded; job queue stopped")


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

    # Generated images live under <runs_dir>/<run_id>/NN_<slot>.png. The
    # frontend constructs URLs of the form /runs/<run_id>/<filename>.
    # check_dir=False skips the at-mount existence check — the lifespan
    # hook creates the directory on startup. Without this, importing
    # this module in a sandbox where the configured runs_dir is not
    # creatable (e.g. CI) raises before any test fixture can redirect
    # the path.
    app.mount(
        "/runs",
        StaticFiles(directory=str(config.runs_dir), check_dir=False),
        name="runs",
    )

    app.include_router(source_router.router)
    app.include_router(debug_router.router)
    app.include_router(runs_router.router)
    app.include_router(slots_router.router)

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

    @app.get("/api/scene-packs")
    def scene_packs() -> dict[str, object]:
        """Return all parseable scene packs from the runtime packs dir.

        Walks the dir on every request — drop-in pack files are picked up
        without a service restart. Bad files surface as warnings rather
        than failing the whole list, so one busted JSON doesn't blank
        the dropdown.
        """
        result = scene_pack.load(config.packs_dir)
        return {
            "packs": [p.model_dump() for p in result.packs],
            "warnings": result.warnings,
            "scene_slot_count": scene_pack.NUM_SCENE_SLOTS,
        }

    @app.get("/api/anchor-variants")
    def anchor_variants() -> dict[str, object]:
        """Return all parseable anchor-variant packs from the runtime dir.

        Same dynamic-discovery semantics as ``/api/scene-packs``. Sparse
        packs are fine — tile dropdowns show whichever packs cover that
        anchor and fall back to the default pack for the rest.
        """
        result = anchor_variant.load(config.packs_dir)
        return {
            "packs": [p.model_dump() for p in result.packs],
            "warnings": result.warnings,
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
