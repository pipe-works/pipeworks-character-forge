"""Tests for the parts of Flux2KleinManager that don't require torch.

The GPU-bound paths (load + i2i + cuda.empty_cache) are exercised on
Luminal via the operator-run /api/debug/i2i endpoint. Here we cover
construction, the early-exit branches, and the unload-when-empty path.
"""

from __future__ import annotations

from pipeworks_character_forge.core.config import config
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager


class TestFlux2KleinManagerLifecycle:
    def test_constructed_without_pipeline(self) -> None:
        manager = Flux2KleinManager(config)
        assert manager.pipeline is None

    def test_unload_is_idempotent_when_pipeline_is_none(self) -> None:
        manager = Flux2KleinManager(config)
        manager.unload()
        manager.unload()
        assert manager.pipeline is None

    def test_unload_drops_pipeline_reference(self) -> None:
        manager = Flux2KleinManager(config)
        manager.pipeline = object()  # bypass real load() — torch not needed
        manager.unload()
        assert manager.pipeline is None
