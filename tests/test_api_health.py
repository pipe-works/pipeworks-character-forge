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
    def test_slots_returns_25_leaves_and_intermediate(self) -> None:
        client = TestClient(create_app())
        response = client.get("/api/slots")
        assert response.status_code == 200
        body = response.json()
        assert body["intermediate"]["id"] == "stylized_base"
        assert len(body["slots"]) == 25
        assert body["slots"][0]["id"] == "turnaround"
        assert body["slots"][-1]["id"] == "golden_hour_rooftop"


class TestIndex:
    def test_index_serves_html(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Character Forge" in response.text
