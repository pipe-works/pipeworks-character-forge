"""Unit tests for the anchor-variant loader, bootstrap, and resolver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeworks_character_forge.api.services import anchor_variant
from pipeworks_character_forge.api.services.anchor_variant import (
    ANCHOR_VARIANTS_SUBDIR,
    AnchorVariantPack,
)


def _write_pack(packs_dir: Path, name: str, variants: dict[str, list[dict]]) -> None:
    target = packs_dir / ANCHOR_VARIANTS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "description": f"Test anchor pack {name}.",
        "variants": variants,
    }
    (target / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _stub_variants(slot_ids: list[str], prefix: str = "v") -> dict[str, list[dict]]:
    return {
        slot_id: [
            {
                "id": f"{prefix}_{slot_id}",
                "label": f"{prefix} {slot_id}",
                "prompt": f"{prefix} prompt for {slot_id}.",
            }
        ]
        for slot_id in slot_ids
    }


class TestAnchorVariantBootstrap:
    def test_seeds_missing_files_from_source(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        (source / "default.json").write_text(
            json.dumps(
                {"name": "default", "label": "Default", "variants": _stub_variants(["turnaround"])}
            )
        )

        packs_dir = tmp_path / "packs"
        anchor_variant.bootstrap(packs_dir, source)

        assert (packs_dir / ANCHOR_VARIANTS_SUBDIR / "default.json").is_file()

    def test_does_not_overwrite_existing_files(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        (source / "default.json").write_text(
            json.dumps(
                {"name": "default", "label": "Default", "variants": _stub_variants(["turnaround"])}
            )
        )

        packs_dir = tmp_path / "packs"
        target_dir = packs_dir / ANCHOR_VARIANTS_SUBDIR
        target_dir.mkdir(parents=True)
        (target_dir / "default.json").write_text("OPERATOR EDIT")

        anchor_variant.bootstrap(packs_dir, source)
        assert (target_dir / "default.json").read_text() == "OPERATOR EDIT"


class TestAnchorVariantLoad:
    def test_loads_well_formed_packs(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "default", _stub_variants(["turnaround", "t_pose"]))
        _write_pack(tmp_path, "photoreal", _stub_variants(["turnaround"], prefix="ph"))

        result = anchor_variant.load(tmp_path)
        assert sorted(p.name for p in result.packs) == ["default", "photoreal"]
        assert result.warnings == []

    def test_skips_pack_whose_name_does_not_match_filename(self, tmp_path: Path) -> None:
        target = tmp_path / ANCHOR_VARIANTS_SUBDIR
        target.mkdir(parents=True)
        (target / "modern.json").write_text(
            json.dumps(
                {"name": "noir", "label": "Noir", "variants": _stub_variants(["turnaround"])}
            )
        )

        result = anchor_variant.load(tmp_path)
        assert result.packs == []
        assert any("modern.json" in w and "noir" in w for w in result.warnings)

    def test_sparse_packs_are_allowed(self, tmp_path: Path) -> None:
        # A pack covering only a subset of anchors loads fine — the
        # tile dropdowns just omit it from the slots it doesn't cover.
        _write_pack(tmp_path, "default", _stub_variants(["turnaround", "t_pose", "smiling"]))
        _write_pack(tmp_path, "expressions_only", _stub_variants(["smiling", "laughing"]))

        result = anchor_variant.load(tmp_path)
        names = {p.name for p in result.packs}
        assert names == {"default", "expressions_only"}
        sparse = next(p for p in result.packs if p.name == "expressions_only")
        assert set(sparse.variants) == {"smiling", "laughing"}

    def test_skips_pack_with_duplicate_variant_ids_in_one_slot(self, tmp_path: Path) -> None:
        target = tmp_path / ANCHOR_VARIANTS_SUBDIR
        target.mkdir(parents=True)
        (target / "broken.json").write_text(
            json.dumps(
                {
                    "name": "broken",
                    "label": "Broken",
                    "variants": {
                        "turnaround": [
                            {"id": "alpha", "label": "Alpha", "prompt": "..."},
                            {"id": "alpha", "label": "Alpha 2", "prompt": "..."},
                        ]
                    },
                }
            )
        )

        result = anchor_variant.load(tmp_path)
        assert result.packs == []
        assert any("duplicate variant ids" in w for w in result.warnings)

    def test_skips_pack_with_no_variants(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "empty", {})
        result = anchor_variant.load(tmp_path)
        assert result.packs == []
        assert any("no variants" in w for w in result.warnings)

    def test_one_bad_pack_does_not_blank_the_others(self, tmp_path: Path) -> None:
        _write_pack(tmp_path, "default", _stub_variants(["turnaround"]))
        target = tmp_path / ANCHOR_VARIANTS_SUBDIR
        (target / "broken.json").write_text("not valid JSON {")

        result = anchor_variant.load(tmp_path)
        assert [p.name for p in result.packs] == ["default"]
        assert any("broken.json" in w for w in result.warnings)


class TestResolveVariant:
    def _packs(self) -> list[AnchorVariantPack]:
        return [
            AnchorVariantPack.model_validate(
                {
                    "name": "default",
                    "label": "Default",
                    "variants": _stub_variants(["turnaround", "t_pose"]),
                }
            ),
            AnchorVariantPack.model_validate(
                {
                    "name": "photoreal",
                    "label": "Photoreal",
                    "variants": _stub_variants(["turnaround"], prefix="ph"),
                }
            ),
        ]

    def test_resolves_known_pack_slot_and_variant(self) -> None:
        v = anchor_variant.resolve_variant(
            self._packs(), "photoreal", "turnaround", "ph_turnaround"
        )
        assert v.id == "ph_turnaround"

    def test_unknown_pack_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="noir"):
            anchor_variant.resolve_variant(self._packs(), "noir", "turnaround", "any")

    def test_pack_does_not_cover_slot_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="does not cover"):
            anchor_variant.resolve_variant(self._packs(), "photoreal", "t_pose", "any")

    def test_unknown_variant_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="not_a_variant"):
            anchor_variant.resolve_variant(self._packs(), "default", "turnaround", "not_a_variant")


class TestDefaultVariantFor:
    def test_returns_first_variant_from_default_pack(self) -> None:
        packs = [
            AnchorVariantPack.model_validate(
                {
                    "name": "default",
                    "label": "Default",
                    "variants": {
                        "turnaround": [
                            {"id": "a", "label": "A", "prompt": "first"},
                            {"id": "b", "label": "B", "prompt": "second"},
                        ]
                    },
                }
            )
        ]
        v = anchor_variant.default_variant_for(packs, "turnaround")
        assert v.id == "a"
        assert v.prompt == "first"

    def test_raises_when_default_pack_absent(self) -> None:
        packs = [
            AnchorVariantPack.model_validate(
                {
                    "name": "photoreal",
                    "label": "Photoreal",
                    "variants": _stub_variants(["turnaround"]),
                }
            )
        ]
        with pytest.raises(ValueError, match="not found"):
            anchor_variant.default_variant_for(packs, "turnaround")

    def test_raises_when_default_pack_does_not_cover_slot(self) -> None:
        packs = [
            AnchorVariantPack.model_validate(
                {
                    "name": "default",
                    "label": "Default",
                    "variants": _stub_variants(["turnaround"]),  # no "t_pose"
                }
            )
        ]
        with pytest.raises(ValueError, match="does not cover"):
            anchor_variant.default_variant_for(packs, "t_pose")
