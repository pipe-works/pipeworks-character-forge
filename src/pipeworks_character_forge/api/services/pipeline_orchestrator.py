"""Sequential 25-slot chain executor.

The orchestrator owns the imperative shape of a run: stylized base first,
then each leaf branches off the stylized base in display order, manifest
updated atomically after every step. Independent of HTTP — exposed via
``api.routers.runs`` and ``api.routers.slots``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from pipeworks_character_forge.api.services.run_store import (
    RunManifest,
    RunStore,
    SlotState,
)
from pipeworks_character_forge.api.services.slot_catalog import SlotCatalog
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager

logger = logging.getLogger(__name__)

# Per-regenerate seed bump — each regen of the same slot gets a distinct
# but reproducible seed. Large enough that a 25-slot run with an order
# space of [0..25] never collides with a regen of any slot.
_REGEN_SEED_STRIDE = 1000


class PipelineOrchestrator:
    """Drives a :class:`Flux2KleinManager` against a :class:`RunStore`.

    Holds no mutable state of its own — all run state is on disk under
    the run dir. Safe to use from a single worker thread; not safe for
    concurrent calls against the same run.
    """

    def __init__(
        self,
        manager: Flux2KleinManager,
        run_store: RunStore,
        catalog: SlotCatalog,
    ) -> None:
        self.manager = manager
        self.run_store = run_store
        self.catalog = catalog

    # -- public chain entry points -----------------------------------------

    def run_full(self, run_id: str) -> None:
        """Generate the stylized base + all 25 leaves, in display order."""
        manifest = self.run_store.load(run_id)
        manifest.status = "running"
        manifest.error = None
        self.run_store.save(manifest)

        try:
            self._generate_slot(manifest, self.catalog.intermediate.id)
            for slot in sorted(self.catalog.slots, key=lambda s: s.order):
                self._generate_slot(manifest, slot.id)
            manifest.status = "done"
        except Exception as exc:
            manifest.status = "failed"
            manifest.error = str(exc)
            self.run_store.save(manifest)
            raise
        else:
            self.run_store.save(manifest)

    def regenerate_slot(self, run_id: str, slot_id: str) -> None:
        """Re-run one slot. Intermediate or leaf; bumps regen_count.

        Does not cascade if ``slot_id`` is the stylized base — children
        keep their existing images. Use :meth:`regenerate_downstream`
        for that.
        """
        manifest = self.run_store.load(run_id)
        if slot_id not in manifest.slots:
            raise KeyError(f"Unknown slot_id: {slot_id!r}")

        manifest.slots[slot_id].regen_count += 1
        manifest.status = "running"
        manifest.error = None
        self.run_store.save(manifest)

        try:
            self._generate_slot(manifest, slot_id)
            manifest.status = "done"
        except Exception as exc:
            manifest.status = "failed"
            manifest.error = str(exc)
            self.run_store.save(manifest)
            raise
        else:
            self.run_store.save(manifest)

    # -- single-slot worker ------------------------------------------------

    def _generate_slot(self, manifest: RunManifest, slot_id: str) -> None:
        """Generate one slot and persist its image + caption + manifest row.

        Reads the latest manifest from disk before each save so a stale
        in-memory copy never overwrites concurrent updates from another
        slot's run (the worker is single-threaded today, but cheap to
        future-proof).
        """
        slot_state = manifest.slots[slot_id]
        slot_state.status = "running"
        slot_state.error = None
        self.run_store.save(manifest)

        rd = self.run_store.run_dir(manifest.run_id)
        ref_path = self._reference_path_for(manifest, slot_id, rd)
        ref = Image.open(ref_path).convert("RGB")

        order = self._order_for(slot_id)
        seed = manifest.params.seed + order + _REGEN_SEED_STRIDE * slot_state.regen_count

        try:
            output = self.manager.i2i(
                ref,
                slot_state.prompt,
                steps=manifest.params.steps,
                guidance=manifest.params.guidance,
                seed=seed,
            )
        except Exception as exc:
            slot_state.status = "failed"
            slot_state.error = str(exc)
            self.run_store.save(manifest)
            raise

        prefix = f"{order:02d}"
        image_filename = f"{prefix}_{slot_id}.png"
        output.save(rd / image_filename)
        slot_state.image = image_filename
        slot_state.seed_used = seed

        # Captions are written for leaves only; the stylized base is an
        # intermediate, not part of the LoRA training set.
        if slot_id != self.catalog.intermediate.id:
            caption_text = self._render_caption(manifest, slot_state.prompt)
            caption_filename = f"{prefix}_{slot_id}.txt"
            (rd / caption_filename).write_text(caption_text + "\n", encoding="utf-8")
            slot_state.caption = caption_filename

        slot_state.status = "done"
        self.run_store.save(manifest)

    # -- helpers -----------------------------------------------------------

    def _reference_path_for(self, manifest: RunManifest, slot_id: str, rd: Path) -> Path:
        if slot_id == self.catalog.intermediate.id:
            return rd / manifest.source_image
        base_image = manifest.slots[self.catalog.intermediate.id].image
        if not base_image:
            raise RuntimeError(
                f"Cannot generate {slot_id!r}: stylized base has not been produced yet."
            )
        return rd / base_image

    def _order_for(self, slot_id: str) -> int:
        slot_def = self.catalog.by_id(slot_id)
        return slot_def.order

    def _render_caption(self, manifest: RunManifest, prompt: str) -> str:
        if manifest.trigger_word:
            return f"{manifest.trigger_word}, {prompt}"
        return prompt

    # Re-export for tests / introspection.
    @staticmethod
    def slot_state(manifest: RunManifest, slot_id: str) -> SlotState:
        return manifest.slots[slot_id]
