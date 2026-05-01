"""Operator-curated scene packs for tiles 17-25.

A scene pack is a JSON file at ``<packs_dir>/scene_packs/<name>.json``
listing one or more scene definitions: ``{id, label, default_prompt}``.
Tiles 17-25 of each run pick a (pack, scene_id) per slot, in any
combination — different packs feed different slots if the operator
wants. The chosen scene's prompt is snapshotted into the manifest at
run-create time, so later edits to the pack file don't retroactively
mutate finished runs.

Discovery is dynamic: every ``GET /api/scene-packs`` request walks the
runtime dir from scratch (3 small JSON files, ~2 ms). The operator can
drop a new pack in, hit refresh, and see it in the dropdown — no
service restart needed.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Subdirectory under ``packs_dir`` reserved for scene packs. Sibling
# subdirs (e.g. ``anchor_variants``) live alongside it under the same
# ``packs/`` parent.
SCENE_PACKS_SUBDIR = "scene_packs"

# Number of scene slots in every run. Locked at 9 to keep the 25-leaf
# layout stable. If you change this, also revise SCENE_SLOT_INDICES.
NUM_SCENE_SLOTS = 9
# Slots 17 through 25, one per scene. Anchor slots occupy 1-16; the
# stylized base is 0.
SCENE_SLOT_INDICES = tuple(range(17, 17 + NUM_SCENE_SLOTS))


class SceneDef(BaseModel):
    """One scene inside a pack."""

    id: str
    label: str
    default_prompt: str


class ScenePack(BaseModel):
    """A loaded pack file. ``name`` is enforced to match the filename."""

    name: str
    label: str
    description: str = ""
    scenes: list[SceneDef] = Field(default_factory=list)


class ScenePackLoadResult(BaseModel):
    """Outcome of walking the runtime packs dir.

    ``packs`` are the successfully-parsed packs; ``warnings`` are
    operator-readable strings describing files that could not be
    loaded. A bad single file does not blank the dropdown.
    """

    packs: list[ScenePack] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def bootstrap(packs_dir: Path, source_dir: Path) -> None:
    """Seed missing scene-pack JSON files from the bundled baselines.

    Idempotent: copies every ``*.json`` from ``source_dir`` into
    ``packs_dir / scene_packs/`` only if the destination doesn't exist.
    Operator edits in the runtime dir win forever — re-deploying the
    package never overwrites their version.
    """
    target_dir = packs_dir / SCENE_PACKS_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.is_dir():
        logger.warning(
            "Bundled scene-pack baseline dir not found at %s; "
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
        logger.info("Seeded %d scene-pack baseline(s) into %s", seeded, target_dir)
    else:
        logger.info("Scene-pack runtime dir already populated at %s", target_dir)


def load(packs_dir: Path) -> ScenePackLoadResult:
    """Walk ``<packs_dir>/scene_packs`` and return parsed packs + warnings.

    Files whose ``name`` field doesn't match the filename are rejected
    (so dropdown grouping can't lie). Files whose JSON or schema is
    bad are skipped with a warning rather than blowing up the request.
    """
    target_dir = packs_dir / SCENE_PACKS_SUBDIR
    result = ScenePackLoadResult()
    if not target_dir.is_dir():
        result.warnings.append(
            f"Scene-pack dir not found at {target_dir}; bootstrap should have created it."
        )
        return result

    for path in sorted(target_dir.glob("*.json")):
        expected_name = path.stem
        try:
            pack = ScenePack.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, ValidationError) as exc:
            result.warnings.append(f"{path.name}: failed to parse — {exc}")
            continue
        if pack.name != expected_name:
            result.warnings.append(
                f"{path.name}: pack name {pack.name!r} does not match filename "
                f"{expected_name!r}; rename one to match the other."
            )
            continue
        # Reject duplicate scene ids within the same pack — they would
        # collide in the dropdown and confuse the operator.
        seen: set[str] = set()
        duplicates: set[str] = set()
        for scene in pack.scenes:
            if scene.id in seen:
                duplicates.add(scene.id)
            seen.add(scene.id)
        if duplicates:
            result.warnings.append(
                f"{path.name}: duplicate scene ids {sorted(duplicates)}; pack skipped."
            )
            continue
        if not pack.scenes:
            result.warnings.append(f"{path.name}: pack has no scenes; skipped.")
            continue
        result.packs.append(pack)

    return result


def resolve_scene(packs: list[ScenePack], pack_name: str, scene_id: str) -> SceneDef:
    """Look up a scene definition by (pack, id). Raises KeyError if absent."""
    for pack in packs:
        if pack.name != pack_name:
            continue
        for scene in pack.scenes:
            if scene.id == scene_id:
                return scene
        raise KeyError(
            f"Scene {scene_id!r} not found in pack {pack_name!r}; "
            f"available: {sorted(s.id for s in pack.scenes)}"
        )
    raise KeyError(f"Pack {pack_name!r} not found; available: {sorted(p.name for p in packs)}")


def default_selections(packs: list[ScenePack]) -> list[tuple[str, str]]:
    """Return 9 ``(pack_name, scene_id)`` pairs for the no-selection fallback.

    The default pack must be present and contain at least 9 scenes —
    otherwise we can't fill all scene slots and the run-create endpoint
    must surface a clear error rather than silently using fewer.
    """
    for pack in packs:
        if pack.name != "default":
            continue
        if len(pack.scenes) < NUM_SCENE_SLOTS:
            raise ValueError(
                f"default scene pack must contain at least {NUM_SCENE_SLOTS} scenes "
                f"to satisfy the no-selection fallback; got {len(pack.scenes)}."
            )
        return [(pack.name, scene.id) for scene in pack.scenes[:NUM_SCENE_SLOTS]]
    raise ValueError(
        "default scene pack not found; no-selection fallback requires "
        "default.json to exist in the runtime packs dir."
    )
