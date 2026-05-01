"""Tests for the parts of Flux2KleinManager that don't require torch.

The GPU-bound paths (load + i2i + cuda.empty_cache) are exercised on
Luminal via the operator-run /api/debug/i2i endpoint. Here we cover
construction, the early-exit branches, the unload-when-empty path, and
the corruption-detection helper that drives auto-recovery from a
mid-forward OOM.
"""

from __future__ import annotations

import pytest

from pipeworks_character_forge.core.config import config
from pipeworks_character_forge.core.flux2_manager import (
    Flux2KleinManager,
    _is_pipeline_corruption,
)


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


class OutOfMemoryError(Exception):  # noqa: N818, A001 — mimic torch's class name
    """Local class with the same __name__ as torch.cuda.OutOfMemoryError.

    The corruption detector matches by class name to avoid an eager
    torch import, so any class literally named ``OutOfMemoryError``
    qualifies — we don't have to depend on torch to test the path.
    """


class TestPipelineCorruptionDetector:
    def test_torch_oom_class_is_corruption(self) -> None:
        # The detector keys on class name to avoid an eager torch import.
        # Any class literally named ``OutOfMemoryError`` qualifies.
        assert _is_pipeline_corruption(OutOfMemoryError("ran out"))

    def test_runtime_error_with_cuda_oom_message_is_corruption(self) -> None:
        assert _is_pipeline_corruption(
            RuntimeError("CUDA out of memory. Tried to allocate 4.00 GiB...")
        )

    def test_runtime_error_with_device_mismatch_is_corruption(self) -> None:
        # The post-OOM symptom that originally motivated this fix.
        assert _is_pipeline_corruption(
            RuntimeError(
                "Expected all tensors to be on the same device, "
                "but found at least two devices, cuda:0 and cpu!"
            )
        )

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad prompt"),
            RuntimeError("unrelated kernel launch failure"),
            KeyError("missing slot"),
        ],
    )
    def test_unrelated_errors_are_not_corruption(self, exc: Exception) -> None:
        assert not _is_pipeline_corruption(exc)


class _RaisingPipeline:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.called = 0

    def __call__(self, **_: object) -> object:
        self.called += 1
        raise self._exc


class TestI2IRecoveryOnCorruption:
    """The manager must drop a corrupted pipeline so the next call rebuilds.

    Without auto-recovery, a single mid-forward OOM poisons the pipeline
    object for the rest of the process's lifetime: every subsequent i2i
    raises a device-mismatch error and the operator has to restart the
    service to recover. With auto-recovery, the operator's next click
    transparently reloads.
    """

    def _ref_image(self) -> object:
        # The pipeline is a fake — the image only needs to be a sentinel
        # the fake doesn't inspect.
        return object()

    def test_oom_unloads_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        torch = pytest.importorskip("torch")
        manager = Flux2KleinManager(config)
        manager.pipeline = _RaisingPipeline(
            RuntimeError("CUDA out of memory. Tried to allocate 4.00 GiB.")
        )
        # Avoid hitting cuda.empty_cache when running on CPU-only hosts.
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            manager.i2i(self._ref_image(), "p", steps=1, guidance=1.0, seed=1)

        assert manager.pipeline is None

    def test_device_mismatch_unloads_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        torch = pytest.importorskip("torch")
        manager = Flux2KleinManager(config)
        manager.pipeline = _RaisingPipeline(
            RuntimeError(
                "Expected all tensors to be on the same device, "
                "but found at least two devices, cuda:0 and cpu!"
            )
        )
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(RuntimeError, match="same device"):
            manager.i2i(self._ref_image(), "p", steps=1, guidance=1.0, seed=1)

        assert manager.pipeline is None

    def test_unrelated_error_keeps_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        torch = pytest.importorskip("torch")
        manager = Flux2KleinManager(config)
        fake = _RaisingPipeline(ValueError("bad prompt"))
        manager.pipeline = fake
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(ValueError, match="bad prompt"):
            manager.i2i(self._ref_image(), "p", steps=1, guidance=1.0, seed=1)

        # Pipeline survives — the error wasn't a corruption signal.
        assert manager.pipeline is fake
