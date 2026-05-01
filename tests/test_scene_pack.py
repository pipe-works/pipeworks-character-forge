"""Unit tests for the scene-pack loader, bootstrap, and resolver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeworks_character_forge.api.services import scene_pack
from pipeworks_character_forge.api.services.scene_pack import (
    NUM_SCENE_SLOTS,
    SCENE_PACKS_SUBDIR,
    SCENE_SLOT_INDICES,
    ScenePack,
)


def _write_pack(packs_dir: Path, name: str, scenes: list[dict[str, str]]) -> None:
    target = packs_dir / SCENE_PACKS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "description": f"Test pack {name}.",
        "scenes": scenes,
    }
    (target / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _stub_scenes(count: int = 9, prefix: str = "stub") -> list[dict[str, str]]:
    return [
        {"id": f"{prefix}_{i}", "label": f"{prefix} {i}", "default_prompt": f"{prefix} prompt {i}."}
        for i in range(count)
    ]


class TestScenePackBootstrap:
    def test_seeds_missing_files_from_source(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        (source / "default.json").write_text(
            json.dumps({"name": "default", "label": "Default", "scenes": _stub_scenes()})
        )

        packs_dir = tmp_path / "packs"
        scene_pack.bootstrap(packs_dir, source)

        assert (packs_dir / SCENE_PACKS_SUBDIR / "default.json").is_file()

    def test_does_not_overwrite_existing_files(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        (source / "default.json").write_text(
            json.dumps({"name": "default", "label": "Default", "scenes": _stub_scenes()})
        )

        packs_dir = tmp_path / "packs"
        target_dir = packs_dir / SCENE_PACKS_SUBDIR
        target_dir.mkdir(parents=True)
        (target_dir / "default.json").write_text("OPERATOR EDIT")

        scene_pack.bootstrap(packs_dir, source)

        # Operator's edit must survive — bootstrap is missing-only.
        assert (target_dir / "default.json").read_text() == "OPERATOR EDIT"

    def test_idempotent(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        (source / "default.json").write_text(
            json.dumps({"name": "default", "label": "Default", "scenes": _stub_scenes()})
        )

        packs_dir = tmp_path / "packs"
        scene_pack.bootstrap(packs_dir, source)
        scene_pack.bootstrap(packs_dir, source)
        # No exception, single file present.
        assert sorted((packs_dir / SCENE_PACKS_SUBDIR).glob("*.json")) == [
            packs_dir / SCENE_PACKS_SUBDIR / "default.json"
        ]


class TestScenePackLoad:
    def test_loads_well_formed_packs(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "default", _stub_scenes())
        _write_pack(tmp_path, "high_fantasy", _stub_scenes(prefix="hf"))

        result = scene_pack.load(tmp_path)
        assert sorted(p.name for p in result.packs) == ["default", "high_fantasy"]
        assert result.warnings == []

    def test_skips_pack_whose_name_does_not_match_filename(self, tmp_path: Path) -> None:
        target = tmp_path / SCENE_PACKS_SUBDIR
        target.mkdir(parents=True)
        # File is named modern.json but inside the pack claims name "noir".
        (target / "modern.json").write_text(
            json.dumps({"name": "noir", "label": "Noir", "scenes": _stub_scenes()})
        )

        result = scene_pack.load(tmp_path)
        assert result.packs == []
        assert any("modern.json" in w and "noir" in w for w in result.warnings)

    def test_skips_pack_with_duplicate_scene_ids(self, tmp_path: Path) -> None:
        scenes = _stub_scenes()
        scenes[2]["id"] = scenes[0]["id"]  # induce a collision
        _write_pack(tmp_path, "broken", scenes)

        result = scene_pack.load(tmp_path)
        assert result.packs == []
        assert any("duplicate scene ids" in w for w in result.warnings)

    def test_skips_pack_with_no_scenes(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "empty", [])
        result = scene_pack.load(tmp_path)
        assert result.packs == []
        assert any("no scenes" in w for w in result.warnings)

    def test_one_bad_pack_does_not_blank_the_others(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "default", _stub_scenes())
        target = tmp_path / SCENE_PACKS_SUBDIR
        (target / "broken.json").write_text("not valid JSON {")

        result = scene_pack.load(tmp_path)
        assert [p.name for p in result.packs] == ["default"]
        assert any("broken.json" in w for w in result.warnings)

    def test_returns_warning_when_scene_packs_dir_missing(self, tmp_path: Path) -> None:
        # No subdirectory created.
        result = scene_pack.load(tmp_path)
        assert result.packs == []
        assert any("not found" in w for w in result.warnings)


class TestResolveScene:
    def _packs(self) -> list[ScenePack]:
        return [
            ScenePack.model_validate(
                {"name": "default", "label": "Default", "scenes": _stub_scenes()}
            ),
            ScenePack.model_validate(
                {
                    "name": "high_fantasy",
                    "label": "High fantasy",
                    "scenes": _stub_scenes(prefix="hf"),
                }
            ),
        ]

    def test_resolves_known_pack_and_scene(self) -> None:
        scene = scene_pack.resolve_scene(self._packs(), "high_fantasy", "hf_3")
        assert scene.id == "hf_3"
        assert scene.label == "hf 3"

    def test_unknown_pack_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="noir"):
            scene_pack.resolve_scene(self._packs(), "noir", "any")

    def test_unknown_scene_in_known_pack_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="not_a_real_scene"):
            scene_pack.resolve_scene(self._packs(), "default", "not_a_real_scene")


class TestDefaultSelections:
    def test_returns_first_nine_scenes_from_default(self) -> None:
        packs = [
            ScenePack.model_validate(
                {"name": "default", "label": "Default", "scenes": _stub_scenes(count=12)}
            ),
        ]
        pairs = scene_pack.default_selections(packs)
        assert len(pairs) == NUM_SCENE_SLOTS == 9
        assert all(p == "default" for p, _ in pairs)
        assert [s for _, s in pairs] == [f"stub_{i}" for i in range(9)]

    def test_raises_when_default_pack_absent(self) -> None:
        packs = [
            ScenePack.model_validate(
                {"name": "modern", "label": "Modern", "scenes": _stub_scenes()}
            )
        ]
        with pytest.raises(ValueError, match="default scene pack not found"):
            scene_pack.default_selections(packs)

    def test_raises_when_default_pack_too_small(self) -> None:
        packs = [
            ScenePack.model_validate(
                {"name": "default", "label": "Default", "scenes": _stub_scenes(count=4)}
            )
        ]
        with pytest.raises(ValueError, match="at least 9 scenes"):
            scene_pack.default_selections(packs)


class TestSceneSlotIndices:
    def test_indices_cover_17_through_25(self) -> None:
        assert SCENE_SLOT_INDICES == (17, 18, 19, 20, 21, 22, 23, 24, 25)
        assert len(SCENE_SLOT_INDICES) == NUM_SCENE_SLOTS
