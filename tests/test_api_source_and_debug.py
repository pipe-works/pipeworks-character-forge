"""Integration tests for /api/source-image and /api/debug/i2i.

Uses a FakeFlux2KleinManager so CI never needs torch, diffusers, or a GPU.
The test config redirects ``runs_dir`` to a tmp path so uploads do not
land in the repo's real ``runs/`` directory.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pipeworks_character_forge.api.dependencies import get_manager
from pipeworks_character_forge.api.main import create_app
from pipeworks_character_forge.core import image_io
from pipeworks_character_forge.core.config import config
from tests._fakes import FakeFlux2KleinManager


def _png_bytes() -> bytes:
    image = Image.new("RGB", (64, 64), color=(200, 50, 50))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def staging_runs_dir(tmp_path, monkeypatch):
    """Redirect config.runs_dir to a tmp path for the duration of the test."""
    monkeypatch.setattr(config, "runs_dir", tmp_path)
    monkeypatch.setattr("pipeworks_character_forge.api.routers.source.config", config)
    monkeypatch.setattr("pipeworks_character_forge.api.routers.debug.config", config)
    return tmp_path


@pytest.fixture
def client(staging_runs_dir):
    app = create_app()
    fake = FakeFlux2KleinManager(config)
    app.state.manager = fake
    app.dependency_overrides[get_manager] = lambda: fake
    with TestClient(app) as test_client:
        test_client.fake_manager = fake  # type: ignore[attr-defined]
        yield test_client


class TestSourceImageUpload:
    def test_returns_source_id_and_dimensions(self, client) -> None:
        response = client.post(
            "/api/source-image",
            files={"file": ("portrait.png", _png_bytes(), "image/png")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["width"] == 64
        assert body["height"] == 64
        assert "source_id" in body

    def test_writes_png_to_staging_dir(self, client, staging_runs_dir) -> None:
        response = client.post(
            "/api/source-image",
            files={"file": ("portrait.png", _png_bytes(), "image/png")},
        )
        source_id = response.json()["source_id"]
        target = staging_runs_dir / "_staging" / f"{source_id}.png"
        assert target.is_file()

    def test_rejects_empty_upload(self, client) -> None:
        response = client.post(
            "/api/source-image",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert response.status_code == 400

    def test_rejects_non_image_payload(self, client) -> None:
        response = client.post(
            "/api/source-image",
            files={"file": ("bad.png", b"not-an-image", "image/png")},
        )
        assert response.status_code == 415


class TestDebugI2I:
    def test_invokes_manager_and_returns_png(self, client, staging_runs_dir) -> None:
        upload = client.post(
            "/api/source-image",
            files={"file": ("portrait.png", _png_bytes(), "image/png")},
        )
        source_id = upload.json()["source_id"]

        response = client.post(
            "/api/debug/i2i",
            data={
                "source_id": source_id,
                "prompt": "Restyle this character.",
                "steps": "12",
                "guidance": "3.5",
                "seed": "9999",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        # Verify the response is a valid PNG of the expected size.
        result = image_io.load_image_bytes(response.content)
        assert result.size == (64, 64)

        # Manager call captured the parameters.
        call = client.fake_manager.calls[-1]
        assert call["prompt"] == "Restyle this character."
        assert call["steps"] == 12
        assert call["guidance"] == 3.5
        assert call["seed"] == 9999

    def test_returns_404_for_unknown_source_id(self, client) -> None:
        response = client.post(
            "/api/debug/i2i",
            data={"source_id": "does-not-exist", "prompt": "x"},
        )
        assert response.status_code == 404
