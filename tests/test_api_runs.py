"""Integration tests for /api/runs and /api/runs/{id}/slots/{slot}/regenerate.

A custom synchronous JobQueue runs jobs in-line on enqueue so the test
asserts post-state without sleeping.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pipeworks_character_forge.api.dependencies import (
    get_job_queue,
    get_manager,
    get_orchestrator,
)
from pipeworks_character_forge.api.main import create_app
from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.api.services.run_store import RunStore
from pipeworks_character_forge.core.config import config

from tests._fakes import FakeFlux2KleinManager


class _SynchronousJobQueue:
    """In-process job runner used in tests instead of the threaded JobQueue.

    Exposes the same enqueue methods the routers depend on, but executes
    each job inline so test assertions can observe the post-state
    immediately.
    """

    def __init__(self, orchestrator: PipelineOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._depth = 0

    def start(self) -> None:
        return None

    def stop(self, timeout: float = 5.0) -> None:
        return None

    def enqueue_full_run(self, run_id: str) -> None:
        self._depth += 1
        try:
            self._orchestrator.run_full(run_id)
        finally:
            self._depth -= 1

    def enqueue_regenerate(self, run_id: str, slot_id: str) -> None:
        self._depth += 1
        try:
            self._orchestrator.regenerate_slot(run_id, slot_id)
        finally:
            self._depth -= 1

    def depth(self) -> int:
        return self._depth


def _png_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(80, 120, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    runs_path = tmp_path / "runs"
    runs_path.mkdir()
    monkeypatch.setattr(config, "runs_dir", runs_path)
    monkeypatch.setattr("pipeworks_character_forge.api.routers.source.config", config)
    monkeypatch.setattr("pipeworks_character_forge.api.routers.debug.config", config)
    monkeypatch.setattr("pipeworks_character_forge.api.routers.runs.config", config)
    return runs_path


@pytest.fixture
def client(runs_dir):
    app = create_app()
    catalog = slot_catalog.load_catalog()
    run_store = RunStore(runs_dir)
    fake_manager = FakeFlux2KleinManager(config)
    orchestrator = PipelineOrchestrator(
        manager=fake_manager, run_store=run_store, catalog=catalog
    )
    sync_queue = _SynchronousJobQueue(orchestrator)

    app.state.manager = fake_manager
    app.state.run_store = run_store
    app.state.orchestrator = orchestrator
    app.state.job_queue = sync_queue

    app.dependency_overrides[get_manager] = lambda: fake_manager
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_job_queue] = lambda: sync_queue

    with TestClient(app) as test_client:
        test_client.fake_manager = fake_manager  # type: ignore[attr-defined]
        test_client.run_store = run_store  # type: ignore[attr-defined]
        yield test_client


def _upload_source(client: TestClient) -> str:
    response = client.post(
        "/api/source-image",
        files={"file": ("portrait.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    return response.json()["source_id"]


class TestCreateRun:
    def test_returns_run_id_and_completes_full_chain(self, client, runs_dir):
        source_id = _upload_source(client)

        response = client.post(
            "/api/runs",
            json={"source_id": source_id, "trigger_word": "trgr"},
        )

        assert response.status_code == 201
        body = response.json()
        run_id = body["run_id"]
        assert body["status"] == "queued"

        # Synchronous queue means by now the chain is finished.
        manifest = client.run_store.load(run_id)
        assert manifest.status == "done"
        assert len(manifest.slots) == 26

    def test_rejects_unknown_source_id(self, client):
        response = client.post(
            "/api/runs",
            json={"source_id": "does-not-exist"},
        )
        assert response.status_code == 404

    def test_rejects_unknown_slot_override(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "slot_overrides": {"nonexistent_slot": "anything"},
            },
        )
        assert response.status_code == 400

    def test_slot_override_lands_in_manifest_and_caption(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "trigger_word": "trgr",
                "slot_overrides": {"smiling": "OVERRIDDEN smile prompt"},
            },
        )
        run_id = response.json()["run_id"]

        manifest = client.run_store.load(run_id)
        smiling = manifest.slots["smiling"]
        assert smiling.prompt == "OVERRIDDEN smile prompt"

        caption_path = client.run_store.run_dir(run_id) / smiling.caption
        assert caption_path.read_text(encoding="utf-8").strip() == (
            "trgr, OVERRIDDEN smile prompt"
        )


class TestGetRun:
    def test_returns_full_manifest(self, client):
        source_id = _upload_source(client)
        run_id = client.post(
            "/api/runs", json={"source_id": source_id}
        ).json()["run_id"]

        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == run_id
        assert body["status"] == "done"
        assert "stylized_base" in body["slots"]

    def test_unknown_run_returns_404(self, client):
        response = client.get("/api/runs/does-not-exist")
        assert response.status_code == 404


class TestListRuns:
    def test_lists_run_ids(self, client):
        source_id = _upload_source(client)
        run_a = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]
        run_b = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        response = client.get("/api/runs")
        assert response.status_code == 200
        ids = response.json()["run_ids"]
        assert run_a in ids
        assert run_b in ids


class TestRegenerateSlot:
    def test_regenerates_one_slot_with_optional_prompt_override(self, client):
        source_id = _upload_source(client)
        run_id = client.post(
            "/api/runs", json={"source_id": source_id}
        ).json()["run_id"]

        before = client.run_store.load(run_id).slots["turnaround"]
        before_calls = len(client.fake_manager.calls)

        response = client.post(
            f"/api/runs/{run_id}/slots/turnaround/regenerate",
            json={"prompt": "REGEN prompt for turnaround"},
        )
        assert response.status_code == 202

        after = client.run_store.load(run_id).slots["turnaround"]
        assert after.regen_count == before.regen_count + 1
        assert after.prompt == "REGEN prompt for turnaround"
        # Exactly one new manager call.
        assert len(client.fake_manager.calls) == before_calls + 1

    def test_unknown_run_returns_404(self, client):
        response = client.post(
            "/api/runs/does-not-exist/slots/turnaround/regenerate",
            json={},
        )
        assert response.status_code == 404

    def test_unknown_slot_returns_404(self, client):
        source_id = _upload_source(client)
        run_id = client.post(
            "/api/runs", json={"source_id": source_id}
        ).json()["run_id"]

        response = client.post(
            f"/api/runs/{run_id}/slots/nonexistent_slot/regenerate",
            json={},
        )
        assert response.status_code == 404
