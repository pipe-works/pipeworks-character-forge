"""Tests for ``pw-forge make-dataset``."""

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
from pipeworks_character_forge.cli import main as cli_main
from pipeworks_character_forge.core.config import config
from tests._fakes import FakeFlux2KleinManager


def _png_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(50, 70, 90))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(config, "runs_dir", runs)
    return runs


def _seed_complete_run(runs_dir: Path, *, trigger_word: str | None = "trgr") -> str:
    """Run the orchestrator end-to-end (with a fake manager) to produce a full run."""
    catalog = slot_catalog.load_catalog()
    store = RunStore(runs_dir)
    manager = FakeFlux2KleinManager(config)
    orchestrator = PipelineOrchestrator(manager=manager, run_store=store, catalog=catalog)

    source_path = runs_dir.parent / "source.png"
    source_path.write_bytes(_png_bytes())

    run_id = "2026-01-01T00-00_aaaaa"
    store.create(
        run_id=run_id,
        source_path=source_path,
        trigger_word=trigger_word,
        params=RunParams(seed=1, steps=2, guidance=1.0),
        catalog=catalog,
    )
    orchestrator.run_full(run_id)
    return run_id


class TestMakeDatasetHappyPath:
    def test_copies_25_image_caption_pairs_excluding_intermediate(self, runs_dir):
        run_id = _seed_complete_run(runs_dir)

        exit_code = cli_main(["make-dataset", run_id])
        assert exit_code == 0

        dataset = runs_dir / run_id / "dataset"
        assert dataset.is_dir()

        pngs = sorted(dataset.glob("*.png"))
        txts = sorted(dataset.glob("*.txt"))
        assert len(pngs) == 25
        assert len(txts) == 25

        # Source, manifest, and stylized_base never make it into the dataset.
        assert not (dataset / "source.png").exists()
        assert not (dataset / "manifest.json").exists()
        assert not (dataset / "00_stylized_base.png").exists()

        # Every PNG has a matching TXT with the same stem.
        png_stems = {p.stem for p in pngs}
        txt_stems = {t.stem for t in txts}
        assert png_stems == txt_stems

    def test_caption_carries_trigger_word_prefix(self, runs_dir):
        run_id = _seed_complete_run(runs_dir, trigger_word="myc")

        cli_main(["make-dataset", run_id])

        text = (runs_dir / run_id / "dataset" / "01_turnaround.txt").read_text(
            encoding="utf-8"
        )
        assert text.startswith("myc,")


class TestMakeDatasetGuards:
    def test_unknown_run_id_returns_1(self, runs_dir):
        assert cli_main(["make-dataset", "does-not-exist"]) == 1

    def test_incomplete_run_returns_2(self, runs_dir, capsys):
        catalog = slot_catalog.load_catalog()
        store = RunStore(runs_dir)
        source_path = runs_dir.parent / "source.png"
        source_path.write_bytes(_png_bytes())
        run_id = "incomplete"
        store.create(
            run_id=run_id,
            source_path=source_path,
            trigger_word=None,
            params=RunParams(),
            catalog=catalog,
        )
        # Manifest status stays at "pending" without orchestrator.run_full().

        assert cli_main(["make-dataset", run_id]) == 2
        err = capsys.readouterr().err
        assert "incomplete" in err.lower() or "pending" in err

    def test_existing_dataset_dir_refused_without_force(self, runs_dir):
        run_id = _seed_complete_run(runs_dir)
        cli_main(["make-dataset", run_id])
        assert cli_main(["make-dataset", run_id]) == 3

    def test_force_overwrites_existing_dataset_dir(self, runs_dir):
        run_id = _seed_complete_run(runs_dir)
        cli_main(["make-dataset", run_id])

        dataset = runs_dir / run_id / "dataset"
        # Drop a stale file the second run should clobber.
        stale = dataset / "stale.txt"
        stale.write_text("stale", encoding="utf-8")
        assert stale.is_file()

        assert cli_main(["make-dataset", run_id, "--force"]) == 0
        assert not stale.exists()


class TestMakeDatasetCustomOutput:
    def test_output_dir_override_lands_outside_run_dir(self, runs_dir, tmp_path):
        run_id = _seed_complete_run(runs_dir)
        target = tmp_path / "custom-export"

        exit_code = cli_main(["make-dataset", run_id, "--output-dir", str(target)])

        assert exit_code == 0
        assert target.is_dir()
        assert len(list(target.glob("*.png"))) == 25


class TestCliDispatch:
    def test_unknown_subcommand_exits_with_argparse_error(self):
        with pytest.raises(SystemExit) as exc_info:
            cli_main(["bogus-subcommand"])
        # argparse exits 2 on unknown subcommand.
        assert exc_info.value.code == 2
