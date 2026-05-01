"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.core.config import config


@pytest.fixture(autouse=True)
def _reset_slot_catalog_cache():
    """Drop the cached SlotCatalog between tests so config tweaks land."""
    slot_catalog.load_catalog.cache_clear()
    yield
    slot_catalog.load_catalog.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_runtime_paths(tmp_path, monkeypatch):
    """Redirect config.runs_dir and config.packs_dir away from /srv/work.

    The lifespan hook in :func:`create_app` calls
    ``scene_pack.bootstrap(config.packs_dir, ...)`` which tries to
    ``mkdir`` the runtime packs dir — that path doesn't exist (and
    isn't writable) on CI. Pointing ``packs_dir`` at the bundled
    package data makes bootstrap a no-op (every bundled file already
    lives under ``data/scene_packs``) and gives every test a clean
    runs_dir under the tmp_path.

    Tests that need to override either path further can do so on top
    of this baseline.
    """
    monkeypatch.setattr(config, "runs_dir", tmp_path / "_isolated_runs")
    monkeypatch.setattr(config, "packs_dir", config.data_dir)
    yield
