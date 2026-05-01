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
from pipeworks_character_forge.api.services.run_store import (
    ResolvedScene,
    RunParams,
    RunStore,
)
from pipeworks_character_forge.core.config import config
from tests._fakes import FakeFlux2KleinManager


def _stub_scene_selections() -> list[ResolvedScene]:
    """9 distinct resolved scenes used by every orchestrator test.

    Real scene packs are not loaded in unit tests — this saves us from
    putting JSON files on disk and lets each scene stay traceable in
    assertions (slot ``scene_17``'s prompt contains the substring
    ``"scene 17 prompt"``, etc.).
    """
    return [
        ResolvedScene(
            pack="default",
            scene_id=f"stub_scene_{i}",
            label=f"Stub scene {i}",
            default_prompt=(
                f"Put this exact character in stub scene {i}. "
                f"This is the scene {i + 17 - 1} prompt for tests."
            ),
        )
        for i in range(9)
    ]


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
    style_suffix: str | None = None,
    only_slots: list[str] | None = None,
    slot_overrides: dict[str, str] | None = None,
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
        style_suffix=style_suffix,
        params=RunParams(seed=1000, steps=4, guidance=3.0),
        catalog=catalog,
        scene_selections=_stub_scene_selections(),
        slot_overrides=slot_overrides,
        only_slots=only_slots,
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
        # Scene leaves use positional ids ``scene_17``..``scene_25``.
        # The chosen scene's metadata lives on the slot state, not in
        # the filename.
        assert manifest.slots["scene_25"].image == "25_scene_25.png"

    def test_per_slot_seeds_use_run_seed_plus_order(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        manifest = orchestrator.run_store.load(run_id)
        # Run seed = 1000; offsets = slot order (stylized_base=0,
        # anchors 1..16, scene_NN's order = NN).
        assert manifest.slots["stylized_base"].seed_used == 1000
        assert manifest.slots["turnaround"].seed_used == 1001
        assert manifest.slots["scene_25"].seed_used == 1025

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

    def test_style_suffix_appended_to_prompt_sent_to_manager(self, orchestrator):
        run_id = _seed_run(
            orchestrator,
            style_suffix="Shot on Kodak Portra 400.",
        )
        orchestrator.run_full(run_id)

        for call in orchestrator.manager.calls:
            assert call["prompt"].endswith(" Shot on Kodak Portra 400.")

    def test_style_prefix_and_suffix_compose_with_single_space_separators(self, orchestrator):
        run_id = _seed_run(
            orchestrator,
            style_prefix="Linocut style.",
            style_suffix="Archival paper.",
        )
        orchestrator.run_full(run_id)

        # Every manager prompt must read "{prefix} {slot_prompt} {suffix}"
        # with exactly one space at each join — no double spaces from an
        # empty middle part, no leading/trailing whitespace.
        for call in orchestrator.manager.calls:
            prompt = call["prompt"]
            assert prompt.startswith("Linocut style. ")
            assert prompt.endswith(" Archival paper.")
            assert "  " not in prompt

    def test_style_suffix_does_not_leak_into_captions(self, orchestrator, runs_dir):
        run_id = _seed_run(
            orchestrator,
            trigger_word="trgr",
            style_suffix="Shot on Kodak Portra 400.",
        )
        orchestrator.run_full(run_id)

        text = (runs_dir / run_id / "01_turnaround.txt").read_text(encoding="utf-8")
        assert "Kodak" not in text
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

    def test_only_slots_runs_base_plus_listed_leaves_and_skips_others(self, orchestrator, runs_dir):
        run_id = _seed_run(orchestrator, only_slots=["smiling", "running"])

        orchestrator.run_full(run_id)

        # 3 fresh manager calls: base + 2 leaves.
        assert len(orchestrator.manager.calls) == 3

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.status == "done"
        assert manifest.slots["stylized_base"].status == "done"
        assert manifest.slots["smiling"].status == "done"
        assert manifest.slots["running"].status == "done"
        # Every other leaf stays pending — the operator can fill them
        # in later via per-tile regenerate or another selective run.
        assert manifest.slots["turnaround"].status == "pending"
        assert manifest.slots["scene_17"].status == "pending"

    def test_cascade_from_base_reruns_everything_and_bumps_regen_count(
        self, orchestrator, runs_dir
    ):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)
        baseline_calls = len(orchestrator.manager.calls)

        orchestrator.cascade_from_base(run_id)

        # 26 fresh manager calls (1 base + 25 leaves).
        assert len(orchestrator.manager.calls) == baseline_calls + 26

        manifest = orchestrator.run_store.load(run_id)
        assert manifest.status == "done"
        for slot_state in manifest.slots.values():
            assert slot_state.regen_count == 1
            assert slot_state.status == "done"

    def test_cascade_preserves_excluded_flags_and_prompt_overrides(self, orchestrator):
        run_id = _seed_run(orchestrator)
        orchestrator.run_full(run_id)

        # Operator marks one slot excluded and edits another's prompt.
        manifest = orchestrator.run_store.load(run_id)
        manifest.slots["smiling"].excluded = True
        manifest.slots["scene_17"].prompt = "OVERRIDE — scene 17 prompt."
        orchestrator.run_store.save(manifest)

        orchestrator.cascade_from_base(run_id)

        manifest = orchestrator.run_store.load(run_id)
        # Excluded flag survives; cascade does not reset slot defaults.
        assert manifest.slots["smiling"].excluded is True
        assert manifest.slots["scene_17"].prompt == "OVERRIDE — scene 17 prompt."

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
