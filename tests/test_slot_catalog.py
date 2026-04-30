"""Invariant tests for the canonical slot catalog."""

from __future__ import annotations

from pipeworks_character_forge.api.services import slot_catalog


class TestSlotCatalogLoading:
    def test_loads_with_25_leaf_slots(self) -> None:
        catalog = slot_catalog.load_catalog()
        assert len(catalog.slots) == 25

    def test_intermediate_is_stylized_base(self) -> None:
        catalog = slot_catalog.load_catalog()
        assert catalog.intermediate.id == "stylized_base"
        assert catalog.intermediate.order == 0

    def test_source_prompt_present(self) -> None:
        catalog = slot_catalog.load_catalog()
        assert "exact character" in catalog.source_prompt.lower()


class TestSlotCatalogInvariants:
    def test_slot_ids_are_unique(self) -> None:
        slots = slot_catalog.list_slots()
        ids = [s.id for s in slots]
        assert len(ids) == len(set(ids))

    def test_slot_orders_are_unique_and_contiguous_1_through_25(self) -> None:
        slots = slot_catalog.list_slots()
        orders = sorted(s.order for s in slots)
        assert orders == list(range(1, 26))

    def test_every_leaf_branches_off_stylized_base(self) -> None:
        slots = slot_catalog.list_slots()
        assert {s.parent for s in slots} == {"stylized_base"}

    def test_groups_match_plan_counts(self) -> None:
        slots = slot_catalog.list_slots()
        counts: dict[str, int] = {}
        for slot in slots:
            counts[slot.group] = counts.get(slot.group, 0) + 1
        assert counts == {
            "reference": 4,
            "portrait": 3,
            "expressions": 5,
            "action": 4,
            "scenes": 9,
        }

    def test_default_prompts_non_empty(self) -> None:
        slots = slot_catalog.list_slots()
        for slot in slots:
            assert slot.default_prompt.strip(), f"slot {slot.id} has empty default_prompt"


class TestSlotCatalogLookup:
    def test_get_returns_intermediate(self) -> None:
        slot = slot_catalog.get("stylized_base")
        assert slot.id == "stylized_base"
        assert slot.group == "intermediate"

    def test_get_returns_leaf(self) -> None:
        slot = slot_catalog.get("turnaround")
        assert slot.order == 1
        assert slot.group == "reference"

    def test_get_unknown_raises_keyerror(self) -> None:
        try:
            slot_catalog.get("nonexistent_slot")
        except KeyError as exc:
            assert "nonexistent_slot" in str(exc)
        else:
            raise AssertionError("expected KeyError for unknown slot id")
