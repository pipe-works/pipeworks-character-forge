"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from pipeworks_character_forge.api.services import slot_catalog


@pytest.fixture(autouse=True)
def _reset_slot_catalog_cache():
    """Drop the cached SlotCatalog between tests so config tweaks land."""
    slot_catalog.load_catalog.cache_clear()
    yield
    slot_catalog.load_catalog.cache_clear()
