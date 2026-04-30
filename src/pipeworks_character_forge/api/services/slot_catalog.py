"""Slot catalog: loads and serves the canonical 25-slot definition.

The catalog is the single source of truth for slot ids, labels, ordering,
default prompts, and parent relationships. The frontend fetches it via
``GET /api/slots`` rather than duplicating the list in JS.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from pipeworks_character_forge.core.config import config


class SlotDef(BaseModel):
    """One slot in the catalog (intermediate or leaf)."""

    id: str
    label: str
    group: str
    order: int
    parent: str
    default_prompt: str


class SlotCatalog(BaseModel):
    """Top-level catalog as loaded from ``data/slots.json``."""

    schema_version: int
    source_prompt: str
    intermediate: SlotDef
    slots: list[SlotDef] = Field(default_factory=list)

    def by_id(self, slot_id: str) -> SlotDef:
        if slot_id == self.intermediate.id:
            return self.intermediate
        for slot in self.slots:
            if slot.id == slot_id:
                return slot
        raise KeyError(f"Unknown slot id: {slot_id!r}")


def _slots_path() -> Path:
    return config.data_dir / "slots.json"


@lru_cache(maxsize=1)
def load_catalog() -> SlotCatalog:
    """Read and validate the slot catalog from disk. Cached for the process."""
    path = _slots_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    catalog = SlotCatalog.model_validate(raw)
    _validate_invariants(catalog)
    return catalog


def list_slots() -> list[SlotDef]:
    """Return all 25 leaf slots in display order. Excludes the intermediate."""
    return sorted(load_catalog().slots, key=lambda s: s.order)


def get(slot_id: str) -> SlotDef:
    """Return a slot by id (intermediate or leaf). Raises KeyError if unknown."""
    return load_catalog().by_id(slot_id)


def _validate_invariants(catalog: SlotCatalog) -> None:
    """Fail loudly on duplicate ids, duplicate orders, or wrong leaf count."""
    ids = [s.id for s in catalog.slots]
    if len(ids) != len(set(ids)):
        raise ValueError("Slot catalog has duplicate ids")
    orders = [s.order for s in catalog.slots]
    if len(orders) != len(set(orders)):
        raise ValueError("Slot catalog has duplicate order values")
    if len(catalog.slots) != 25:
        raise ValueError(f"Slot catalog must contain 25 leaf slots, got {len(catalog.slots)}")
    if catalog.intermediate.order != 0:
        raise ValueError("Intermediate slot must have order=0")
    for slot in catalog.slots:
        if slot.parent != catalog.intermediate.id:
            raise ValueError(
                f"Slot {slot.id!r} parent={slot.parent!r}, expected "
                f"{catalog.intermediate.id!r} (every leaf branches off the stylized base)"
            )
