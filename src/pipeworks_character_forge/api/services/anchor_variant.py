"""Operator-curated phrasing variants for the 17 anchor slots.

A variant pack is a JSON file at
``<packs_dir>/anchor_variants/<name>.json`` listing alternative
phrasings keyed by anchor slot id (``stylized_base``, ``turnaround``,
``t_pose``, ..., ``leaning``). Each anchor slot can be filled by a
``(pack, variant_id)`` pick — the picker dropdown in the tile shows
every variant from every pack that covers that slot, grouped by pack.

A pack does not need to cover every anchor — packs declare what they
cover, and tiles fall back to the catalog default for anchors a pack
omits. This lowers the bar for operator-written packs ("here's my
three favourite turnaround phrasings — nothing else").

The bundled ``default`` pack is required and must cover every anchor:
it backs the dropdown's first option and the no-selection fallback.

Discovery is dynamic — every ``GET /api/anchor-variants`` request
walks the dir, so dropping a new pack in is picked up without a
service restart. Bad files surface as warnings, never blank the
dropdown.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Subdirectory under ``packs_dir`` reserved for anchor variant packs.
# Sits alongside ``scene_packs/`` from PR 2.
ANCHOR_VARIANTS_SUBDIR = "anchor_variants"

# The pack name that backs the dropdown's first option and the
# no-selection fallback. Must exist in the runtime dir; bootstrap
# guarantees this on first deploy.
DEFAULT_PACK_NAME = "default"


class AnchorVariant(BaseModel):
    """One phrasing alternative for one anchor slot inside one pack."""

    id: str
    label: str
    prompt: str


class AnchorVariantPack(BaseModel):
    """A loaded pack file. ``name`` is enforced to match the filename."""

    name: str
    label: str
    description: str = ""
    # Keyed by anchor slot id. Sparse coverage is allowed — a pack may
    # ship variants for a subset of anchors and the tile dropdowns
    # simply omit that pack from the slots it doesn't cover.
    variants: dict[str, list[AnchorVariant]] = Field(default_factory=dict)


class AnchorVariantPackLoadResult(BaseModel):
    """Outcome of walking the runtime anchor-variants dir.

    ``packs`` are the successfully-parsed packs; ``warnings`` are
    operator-readable strings describing files that could not be
    loaded. A bad single file does not blank the dropdowns.
    """

    packs: list[AnchorVariantPack] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def bootstrap(packs_dir: Path, source_dir: Path) -> None:
    """Seed missing anchor-variant JSON files from the bundled baselines.

    Idempotent: copies every ``*.json`` from ``source_dir`` into
    ``packs_dir / anchor_variants/`` only if the destination doesn't
    exist. Operator edits in the runtime dir win forever — re-deploying
    the package never overwrites their version.
    """
    target_dir = packs_dir / ANCHOR_VARIANTS_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.is_dir():
        logger.warning(
            "Bundled anchor-variants baseline dir not found at %s; "
            "operator must drop pack files into %s manually.",
            source_dir,
            target_dir,
        )
        return

    seeded = 0
    for src in sorted(source_dir.glob("*.json")):
        dst = target_dir / src.name
        if dst.exists():
            continue
        shutil.copyfile(src, dst)
        seeded += 1
    if seeded:
        logger.info("Seeded %d anchor-variant baseline(s) into %s", seeded, target_dir)
    else:
        logger.info("Anchor-variant runtime dir already populated at %s", target_dir)


def load(packs_dir: Path) -> AnchorVariantPackLoadResult:
    """Walk ``<packs_dir>/anchor_variants`` and return parsed packs + warnings.

    Files whose ``name`` field doesn't match the filename are rejected
    so dropdown grouping can't lie. Files whose JSON or schema is bad
    are skipped with a warning rather than blowing up the request.
    """
    target_dir = packs_dir / ANCHOR_VARIANTS_SUBDIR
    result = AnchorVariantPackLoadResult()
    if not target_dir.is_dir():
        result.warnings.append(
            f"Anchor-variants dir not found at {target_dir}; " "bootstrap should have created it."
        )
        return result

    for path in sorted(target_dir.glob("*.json")):
        expected_name = path.stem
        try:
            pack = AnchorVariantPack.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, ValidationError) as exc:
            result.warnings.append(f"{path.name}: failed to parse — {exc}")
            continue
        if pack.name != expected_name:
            result.warnings.append(
                f"{path.name}: pack name {pack.name!r} does not match filename "
                f"{expected_name!r}; rename one to match the other."
            )
            continue
        # Reject duplicate variant ids within the same (pack, slot).
        # Different slots may share a variant id — that's fine; the
        # full key is (pack, slot, variant_id).
        ok = True
        for slot_id, variants in pack.variants.items():
            seen: set[str] = set()
            duplicates: set[str] = set()
            for v in variants:
                if v.id in seen:
                    duplicates.add(v.id)
                seen.add(v.id)
            if duplicates:
                result.warnings.append(
                    f"{path.name}: slot {slot_id!r} has duplicate variant ids "
                    f"{sorted(duplicates)}; pack skipped."
                )
                ok = False
                break
        if not ok:
            continue
        if not pack.variants:
            result.warnings.append(f"{path.name}: pack has no variants; skipped.")
            continue
        result.packs.append(pack)

    return result


def resolve_variant(
    packs: list[AnchorVariantPack],
    pack_name: str,
    slot_id: str,
    variant_id: str,
) -> AnchorVariant:
    """Look up a variant by (pack, slot, variant_id). KeyError if absent."""
    for pack in packs:
        if pack.name != pack_name:
            continue
        slot_variants = pack.variants.get(slot_id)
        if not slot_variants:
            raise KeyError(
                f"Pack {pack_name!r} does not cover slot {slot_id!r}; "
                f"covers: {sorted(pack.variants)}"
            )
        for v in slot_variants:
            if v.id == variant_id:
                return v
        raise KeyError(
            f"Variant {variant_id!r} not found in pack {pack_name!r} for slot "
            f"{slot_id!r}; available: {sorted(v.id for v in slot_variants)}"
        )
    raise KeyError(f"Pack {pack_name!r} not found; available: {sorted(p.name for p in packs)}")


def default_variant_for(packs: list[AnchorVariantPack], slot_id: str) -> AnchorVariant:
    """Return the first variant of ``slot_id`` from the default pack.

    The default pack must cover every anchor — otherwise the no-selection
    fallback can't fill a tile and the run-create endpoint must surface
    a clear error rather than silently leaving a slot empty.
    """
    for pack in packs:
        if pack.name != DEFAULT_PACK_NAME:
            continue
        variants = pack.variants.get(slot_id)
        if not variants:
            raise ValueError(
                f"Default anchor-variant pack does not cover slot {slot_id!r}; "
                "default.json must define a variant for every anchor."
            )
        return variants[0]
    raise ValueError(
        f"Default anchor-variant pack {DEFAULT_PACK_NAME!r} not found; "
        "no-selection fallback requires default.json to exist in the "
        "runtime packs dir."
    )
