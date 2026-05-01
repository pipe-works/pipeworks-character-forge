"""Smoke tests for the PR 1 API surface: /api/health, /api/slots, /."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pipeworks_character_forge.api.main import create_app


class TestApiHealth:
    def test_health_returns_ok(self) -> None:
        client = TestClient(create_app())
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "version" in body


class TestApiSlots:
    def test_slots_returns_16_anchors_and_intermediate(self) -> None:
        # /api/slots returns the anchor catalog only — scenes (17-25)
        # are exposed via /api/scene-packs in PR 2.
        client = TestClient(create_app())
        response = client.get("/api/slots")
        assert response.status_code == 200
        body = response.json()
        assert body["intermediate"]["id"] == "stylized_base"
        assert len(body["slots"]) == 16
        assert body["slots"][0]["id"] == "turnaround"
        assert body["slots"][-1]["id"] == "leaning"


class TestApiScenePacks:
    def test_returns_bundled_packs(self, tmp_path, monkeypatch) -> None:
        # Point packs_dir at the bundled package data so the loader sees
        # ``data/scene_packs/*.json`` directly without running bootstrap.
        from pipeworks_character_forge.core.config import config

        monkeypatch.setattr(config, "packs_dir", config.data_dir)
        client = TestClient(create_app())
        response = client.get("/api/scene-packs")
        assert response.status_code == 200
        body = response.json()
        names = {p["name"] for p in body["packs"]}
        # The default pack is required by the no-selection fallback;
        # the others are nice-to-have alternates the operator can extend.
        assert "default" in names
        assert body["scene_slot_count"] == 9


class TestApiAnchorVariants:
    def test_returns_bundled_packs(self, tmp_path, monkeypatch) -> None:
        from pipeworks_character_forge.core.config import config

        monkeypatch.setattr(config, "packs_dir", config.data_dir)
        client = TestClient(create_app())
        response = client.get("/api/anchor-variants")
        assert response.status_code == 200
        body = response.json()
        names = {p["name"] for p in body["packs"]}
        assert "default" in names
        # Default pack must cover every anchor — required by the
        # no-selection fallback in the run-create router.
        default_pack = next(p for p in body["packs"] if p["name"] == "default")
        assert "turnaround" in default_pack["variants"]
        assert "stylized_base" in default_pack["variants"]


class TestIndex:
    def test_index_serves_html(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Character Forge" in response.text
