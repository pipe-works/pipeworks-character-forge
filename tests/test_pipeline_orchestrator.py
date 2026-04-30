"""Tests for the 25-slot pipeline orchestrator using a fake manager."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from pipeworks_character_forge.api.services.run_store import RunParams, RunStore
from pipeworks_character_forge.core.config import config
from tests._fakes import FakeFlux2KleinManager


def _png_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = Image.new("RGB", (32, 32), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes())


@pytest.fixture
def runs_dir(tmp_path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def run_store(runs_dir) -> RunStore:
    return RunStore(runs_dir)


@pytest.fixture
def orchestrator(run_store) -> PipelineOrchestrator:
    catalog = slot_catalog.load_catalog()
    manager = FakeFlux2KleinManager(config)
    return PipelineOrchestrator(manager=manager, run_store=run_store, catalog=catalog)


def _seed_run(
    orchestrator: PipelineOrchestrator,
    *,
    trigger_word: str | None = None,
    style_prefix: str | None = None,
) -> str:
    run_id = "test-run"
    catalog = slot_catalog.load_catalog()
    source_path = orchestrator.run_store.runs_dir.parent / "source.png"
    _write_source(source_path)
    orchestrator.run_store.create(
        run_id=run_id,
        source_path=source_path,
        trigger_word=trigger_word,
        style_prefix=style_prefix,
        params=RunParams(seed=1000, steps=4, guidance=3.0),
        catalog=catalog,
    )
    return run_id


class TestRunFull:
    def test_generates_stylized_base_plus_25_leaves(self, orchestrator, runs_dir):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.status == "done"
        assert len(manifest.slots) == 26  # stylized_base + 25
        for slot_state in manifest.slots.values():
            assert slot_state.status == "done"
            assert slot_state.image is not None
            assert (runs_dir / run_id / slot_state.image).is_file()

    def test_writes_captions_for_leaves_only(self, orchestrator, runs_dir):
        run_id = _seed_run(orchestrator, trigger_word="charname")
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        # Stylized base never has a caption.
        assert manifest.slots["stylized_base"].caption is None
        # Every leaf has a caption file with the trigger word prefixed.
        for slot_id, slot_state in manifest.slots.items():
            if slot_id == "stylized_base":
                continue
            assert slot_state.caption is not None
            caption_path = runs_dir / run_id / slot_state.caption
            assert caption_path.is_file()
            text = caption_path.read_text(encoding="utf-8").strip()
            assert text.startswith("charname,")

    def test_writes_bare_caption_when_no_trigger_word(self, orchestrator, runs_dir):
        run_id = _seed_run(orchestrator, trigger_word=None)
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        turnaround = manifest.slots["turnaround"]
        text = (runs_dir / run_id / turnaround.caption).read_text(encoding="utf-8").strip()
        # No trigger word, so the caption is just the prompt verbatim.
        assert text == turnaround.prompt

    def test_image_filenames_follow_nn_slot_pattern(self, orchestrator, runs_dir):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.slots["stylized_base"].image == "00_stylized_base.png"
        assert manifest.slots["turnaround"].image == "01_turnaround.png"
        assert manifest.slots["golden_hour_rooftop"].image == "25_golden_hour_rooftop.png"

    def test_per_slot_seeds_use_run_seed_plus_order(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        # Run seed = 1000; offsets = slot order (stylized_base=0, leaves 1..25).
        assert manifest.slots["stylized_base"].seed_used == 1000
        assert manifest.slots["turnaround"].seed_used == 1001
        assert manifest.slots["golden_hour_rooftop"].seed_used == 1025

    def test_failure_marks_run_failed_and_re_raises(self, orchestrator):
        run_id = _seed_run(orchestrator)

        def boom(*args, **kwargs):
            raise RuntimeError("synthetic failure")

        orchestrator.manager.i2i = boom  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="synthetic failure"):
            orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.status == "failed"
        assert manifest.error == "synthetic failure"
        # The slot we tried first should be marked failed too.
        assert manifest.slots["stylized_base"].status == "failed"


class TestRegenerateSlot:
    def test_regen_increments_count_and_changes_seed(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)
        first = orchestrator.run_store.load(run_id).slots["turnaround"].seed_used

        orchestrator.regenerate_slot(run_id, "turnaround")

        manifest = orchestrator.run_store.load(run_id)
        slot = manifest.slots["turnaround"]
        assert slot.regen_count == 1
        # Seed = base + order + 1000 * regen_count = 1000 + 1 + 1000 = 2001.
        assert slot.seed_used == first + 1000

    def test_regen_only_runs_one_slot(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)
        baseline_calls = len(orchestrator.manager.calls)

        orchestrator.regenerate_slot(run_id, "smiling")

        # Exactly one new manager call, prompt matching the smiling slot.
        assert len(orchestrator.manager.calls) == baseline_calls + 1
        assert "smile" in orchestrator.manager.calls[-1]["prompt"].lower()

    def test_regen_unknown_slot_raises_keyerror(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)
        with pytest.raises(KeyError):
            orchestrator.regenerate_slot(run_id, "nonexistent_slot")

    def test_style_prefix_prepended_to_prompt_sent_to_manager(self, orchestrator, runs_dir):
        run_id = _seed_run(
            orchestrator,
            trigger_word="trgr",
            style_prefix="Linocut style with muted sepia palette.",
        )
        orchestrator.run_full(run_id)

        # Every manager call's prompt must start with the style prefix
        # plus a single space separator before the slot's own text.
        for call in orchestrator.manager.calls:
            assert call["prompt"].startswith("Linocut style with muted sepia palette. ")

    def test_style_prefix_does_not_leak_into_captions(self, orchestrator, runs_dir):
        run_id = _seed_run(
            orchestrator,
            trigger_word="trgr",
            style_prefix="Linocut style with muted sepia palette.",
        )
        orchestrator.run_full(run_id)

        text = (runs_dir / run_id / "01_turnaround.txt").read_text(encoding="utf-8")
        assert "Linocut" not in text
        assert text.startswith("trgr,")

    def test_cancel_between_slots_marks_run_cancelled_and_preserves_partials(
        self, orchestrator, runs_dir
    ):
        run_id = _seed_run(orchestrator)

        # Wrap the manager so we cancel after the 3rd i2i call.
        original_i2i = orchestrator.manager.i2i
        call_count = {"n": 0}

        def cancel_after_third(*args, **kwargs):
            result = original_i2i(*args, **kwargs)
            call_count["n"] += 1
            if call_count["n"] == 3:
                manifest = orchestrator.run_store.load(run_id)
                manifest.cancel_requested = True
                orchestrator.run_store.save(manifest)
            return result

        orchestrator.manager.i2i = cancel_after_third  # type: ignore[method-assign]

        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.status == "cancelled"
        assert manifest.cancel_requested is False  # cleared on finalize

        done = [s for s in manifest.slots.values() if s.status == "done"]
        pending = [s for s in manifest.slots.values() if s.status == "pending"]
        assert len(done) == 3
        assert len(pending) == len(manifest.slots) - 3

        # Done slots' PNGs stayed on disk.
        for slot_state in done:
            assert (runs_dir / run_id / slot_state.image).is_file()

    def test_regen_uses_stylized_base_as_reference_for_leaves(self, orchestrator):
        """Every leaf regen reads <run>/00_stylized_base.png, not the source."""
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        # Capture which file the manager last received.
        sizes_before = [call["ref_size"] for call in orchestrator.manager.calls if call["ref_size"]]
        assert sizes_before  # at least some calls happened

        orchestrator.regenerate_slot(run_id, "running")
        # The ref_size for the new call is the size of the fake-painted
        # stylized_base.png on disk, which equals the source size (32×32)
        # because the fake manager preserves reference dimensions.
        assert orchestrator.manager.calls[-1]["ref_size"] == (32, 32)
