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

    def enqueue_cascade(self, run_id: str) -> None:
        self._depth += 1
        try:
            self._orchestrator.cascade_from_base(run_id)
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
    # Point packs_dir at the bundled package data so the no-selection
    # fallback path (default.json with 9 scenes) resolves without us
    # having to run the bootstrap copy step in every test.
    monkeypatch.setattr(config, "packs_dir", config.data_dir)
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
    orchestrator = PipelineOrchestrator(manager=fake_manager, run_store=run_store, catalog=catalog)
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
        assert caption_path.read_text(encoding="utf-8").strip() == ("trgr, OVERRIDDEN smile prompt")


class TestGetRun:
    def test_returns_full_manifest(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

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


class TestAnchorVariantSelections:
    def test_default_fallback_records_default_pack_on_every_anchor(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        manifest = client.run_store.load(run_id)
        # Every anchor (intermediate + 16 leaves) must have variant_pack
        # set — the no-pick fallback fills them from default.json.
        for anchor_id in ["stylized_base", "turnaround", "smiling", "leaning"]:
            slot = manifest.slots[anchor_id]
            assert slot.variant_pack == "default"
            assert slot.variant_id == "default"

    def test_explicit_anchor_pick_drives_prompt_and_snapshot(self, client):
        source_id = _upload_source(client)
        # Pick the photoreal pack's variant for "turnaround" only;
        # everything else falls back to default.
        run_id = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "anchor_variants": {
                    "turnaround": {"pack": "photoreal", "variant_id": "studio_sheet"}
                },
            },
        ).json()["run_id"]

        manifest = client.run_store.load(run_id)
        assert manifest.slots["turnaround"].variant_pack == "photoreal"
        assert manifest.slots["turnaround"].variant_id == "studio_sheet"
        assert "Photograph" in manifest.slots["turnaround"].prompt
        # Other anchors stayed on the default pack.
        assert manifest.slots["t_pose"].variant_pack == "default"

    def test_unknown_anchor_pack_returns_400(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "anchor_variants": {"turnaround": {"pack": "does_not_exist", "variant_id": "x"}},
            },
        )
        assert response.status_code == 400

    def test_unknown_anchor_slot_id_returns_400(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "anchor_variants": {
                    "not_a_real_anchor": {"pack": "default", "variant_id": "default"}
                },
            },
        )
        assert response.status_code == 400


class TestSceneSelections:
    def test_default_fallback_fills_scenes_from_default_pack(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        manifest = client.run_store.load(run_id)
        # All 9 scene slots present, all materialised from the default
        # pack, with snapshot fields populated from the pack file.
        for index in range(17, 26):
            slot = manifest.slots[f"scene_{index}"]
            assert slot.scene_pack == "default"
            assert slot.scene_id, f"scene_{index} missing scene_id"
            assert slot.scene_label, f"scene_{index} missing scene_label"

    def test_explicit_picks_drive_scene_label_and_prompt(self, client):
        source_id = _upload_source(client)
        # Pick the same pack/scene for every slot; this is artificial
        # but confirms the selection pipeline plumbs through end-to-end.
        selections = [{"pack": "default", "scene_id": "neon_alley"}] * 9
        run_id = client.post(
            "/api/runs",
            json={"source_id": source_id, "scene_selections": selections},
        ).json()["run_id"]

        manifest = client.run_store.load(run_id)
        for index in range(17, 26):
            slot = manifest.slots[f"scene_{index}"]
            assert slot.scene_id == "neon_alley"
            assert slot.scene_label == "Neon alley"
            assert "neon-lit alley" in slot.prompt

    def test_unknown_pack_returns_400(self, client):
        source_id = _upload_source(client)
        selections = [{"pack": "does_not_exist", "scene_id": "x"}] * 9
        response = client.post(
            "/api/runs",
            json={"source_id": source_id, "scene_selections": selections},
        )
        assert response.status_code == 400

    def test_unknown_scene_in_known_pack_returns_400(self, client):
        source_id = _upload_source(client)
        selections = [{"pack": "default", "scene_id": "no_such_scene"}] * 9
        response = client.post(
            "/api/runs",
            json={"source_id": source_id, "scene_selections": selections},
        )
        assert response.status_code == 400

    def test_wrong_count_returns_400(self, client):
        source_id = _upload_source(client)
        selections = [{"pack": "default", "scene_id": "neon_alley"}] * 5
        response = client.post(
            "/api/runs",
            json={"source_id": source_id, "scene_selections": selections},
        )
        assert response.status_code == 400


class TestSelectiveRun:
    def test_only_slots_runs_base_plus_listed_leaves(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "only_slots": ["smiling", "scene_17"],
            },
        )
        assert response.status_code == 201
        run_id = response.json()["run_id"]

        # Synchronous queue: chain has already finished.
        manifest = client.run_store.load(run_id)
        assert manifest.status == "done"
        assert manifest.slots["stylized_base"].status == "done"
        assert manifest.slots["smiling"].status == "done"
        assert manifest.slots["scene_17"].status == "done"
        assert manifest.slots["turnaround"].status == "pending"

    def test_only_slots_strips_stylized_base_silently(self, client):
        # Operator ticks stylized_base + a leaf; the API should accept
        # this and run base+leaf normally (base runs implicitly always).
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "only_slots": ["stylized_base", "smiling"],
            },
        )
        assert response.status_code == 201
        run_id = response.json()["run_id"]

        manifest = client.run_store.load(run_id)
        # Persisted only_slots has the base stripped (it's implicit).
        assert manifest.only_slots == ["smiling"]

    def test_unknown_slot_in_only_slots_returns_400(self, client):
        source_id = _upload_source(client)
        response = client.post(
            "/api/runs",
            json={
                "source_id": source_id,
                "only_slots": ["nonexistent_slot"],
            },
        )
        assert response.status_code == 400


class TestCascadeRun:
    def test_cascade_reruns_full_chain_on_existing_run(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]
        baseline_calls = len(client.fake_manager.calls)

        response = client.post(f"/api/runs/{run_id}/cascade")
        assert response.status_code == 202
        # Synchronous queue ran the cascade inline; expect 26 fresh calls.
        assert len(client.fake_manager.calls) == baseline_calls + 26

    def test_cascade_unknown_run_returns_404(self, client):
        response = client.post("/api/runs/does-not-exist/cascade")
        assert response.status_code == 404

    def test_cascade_running_run_returns_409(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]
        # Manually flip status back to running and try to cascade.
        manifest = client.run_store.load(run_id)
        manifest.status = "running"
        client.run_store.save(manifest)
        response = client.post(f"/api/runs/{run_id}/cascade")
        assert response.status_code == 409


class TestPatchSlot:
    def test_marks_slot_excluded(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        response = client.patch(
            f"/api/runs/{run_id}/slots/smiling",
            json={"excluded": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["excluded"] is True

        # Persisted to the manifest.
        manifest = client.run_store.load(run_id)
        assert manifest.slots["smiling"].excluded is True

    def test_unknown_run_or_slot_returns_404(self, client):
        bad_run = client.patch(
            "/api/runs/does-not-exist/slots/smiling",
            json={"excluded": True},
        )
        assert bad_run.status_code == 404

        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        bad_slot = client.patch(
            f"/api/runs/{run_id}/slots/nonexistent_slot",
            json={"excluded": True},
        )
        assert bad_slot.status_code == 404

    def test_dataset_export_skips_excluded_slots(self, client):
        source_id = _upload_source(client)
        run_id = client.post(
            "/api/runs", json={"source_id": source_id, "trigger_word": "trgr"}
        ).json()["run_id"]

        client.patch(
            f"/api/runs/{run_id}/slots/scene_17",
            json={"excluded": True},
        )

        response = client.post(f"/api/runs/{run_id}/dataset")
        assert response.status_code == 201
        body = response.json()
        assert body["pairs"] == 24
        assert "scene_17" in body["excluded"]


class TestCancelRun:
    def test_cancel_sets_flag_on_running_manifest(self, client, runs_dir):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        # Synchronous queue ran the chain to completion; flip the
        # manifest back to "running" so we can exercise the cancel
        # endpoint's success path.
        manifest = client.run_store.load(run_id)
        manifest.status = "running"
        client.run_store.save(manifest)

        response = client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code == 202
        assert response.json()["status"] == "cancel_requested"

        manifest = client.run_store.load(run_id)
        assert manifest.cancel_requested is True

    def test_cancel_unknown_run_returns_404(self, client):
        response = client.post("/api/runs/does-not-exist/cancel")
        assert response.status_code == 404

    def test_cancel_done_run_returns_409(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]
        # Synchronous queue means this run is already 'done'.
        response = client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code == 409


class TestRegenerateSlot:
    def test_regenerates_one_slot_with_optional_prompt_override(self, client):
        source_id = _upload_source(client)
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

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
        run_id = client.post("/api/runs", json={"source_id": source_id}).json()["run_id"]

        response = client.post(
            f"/api/runs/{run_id}/slots/nonexistent_slot/regenerate",
            json={},
        )
        assert response.status_code == 404
