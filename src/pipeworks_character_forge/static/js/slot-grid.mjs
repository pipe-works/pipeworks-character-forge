// Renders the 26-tile grid and applies manifest updates from the
// progress poller. Layout is:
//   - 1 stylized-base tile (promoted)
//   - 16 anchor tiles from the slot catalog (orders 1-16)
//   - 9 scene tiles populated from the loaded scene packs (orders 17-25)
// The 9 scene tiles each carry a <select> dropdown so the operator
// can swap which scene fills the slot independently.

import { patchSlot, regenerateSlot } from "./run-client.mjs";
import { createSlotTile } from "./slot-tile.mjs";

const SCENE_SLOT_INDICES = [17, 18, 19, 20, 21, 22, 23, 24, 25];

export function createSlotGrid(rootEl, catalog, scenePackResult, anchorVariantResult) {
  // Order is enforced by /api/slots: intermediate first, then anchors
  // sorted by `order`. Scene leaves come from /api/scene-packs and are
  // appended after the anchor tiles in positions 17-25.
  const tilesById = new Map();
  const scenePacks = scenePackResult?.packs ?? [];
  const anchorVariantPacks = anchorVariantResult?.packs ?? [];
  // The "default" pack is the no-selection fallback. Pre-pick its
  // first 9 scenes so a fresh page reads sensibly even if the operator
  // never touches the dropdowns. Loader guarantees default has >= 9
  // scenes (run-create errors loudly otherwise).
  const defaultPack = scenePacks.find((p) => p.name === "default");
  const defaultAnchorPack = anchorVariantPacks.find((p) => p.name === "default");

  function _initialAnchorPick(slotId) {
    // Default-pack first variant for this slot, mirroring the server-
    // side fallback. Returns null if for some reason the default pack
    // doesn't cover this anchor (loader should prevent that, but be
    // defensive — the picker just renders empty rather than crashing).
    const variants = defaultAnchorPack?.variants?.[slotId];
    if (!Array.isArray(variants) || variants.length === 0) return null;
    return { pack: defaultAnchorPack.name, variant_id: variants[0].id };
  }

  function _anchorTileOpts(slotDef, extra = {}) {
    const initial = _initialAnchorPick(slotDef.id);
    return {
      ...extra,
      anchorVariantPicker: anchorVariantPacks.length
        ? { packs: anchorVariantPacks, initial }
        : null,
    };
  }

  // Promoted base tile.
  const baseTile = createSlotTile(
    catalog.intermediate,
    _anchorTileOpts(catalog.intermediate, { promoted: true }),
  );
  tilesById.set(catalog.intermediate.id, baseTile);
  rootEl.appendChild(baseTile.root);

  // Anchor leaves.
  for (const slotDef of catalog.slots) {
    const tile = createSlotTile(slotDef, _anchorTileOpts(slotDef));
    tilesById.set(slotDef.id, tile);
    rootEl.appendChild(tile.root);
  }

  // Scene leaves. Slot ids are positional (``scene_17`` through
  // ``scene_25``) — the actual scene chosen is metadata on the tile,
  // not the id, so the tile id is stable across pack swaps.
  SCENE_SLOT_INDICES.forEach((order, idx) => {
    const initialScene = defaultPack?.scenes?.[idx];
    const initialPick = initialScene
      ? { pack: defaultPack.name, scene_id: initialScene.id }
      : null;
    const sceneSlotDef = {
      id: `scene_${order}`,
      label: initialScene?.label ?? `Scene ${order}`,
      group: "scenes",
      order,
      parent: catalog.intermediate.id,
      default_prompt: initialScene?.default_prompt ?? "",
    };
    const tile = createSlotTile(sceneSlotDef, {
      scenePicker: { packs: scenePacks, initial: initialPick },
    });
    tilesById.set(sceneSlotDef.id, tile);
    rootEl.appendChild(tile.root);
  });

  // ---- per-tile interaction --------------------------------------------

  // Track per-slot prompt overrides so a manifest update doesn't clobber
  // user edits made before the chain has caught up to that slot.
  const promptOverrides = new Map();
  // Track per-slot picker overrides — set when the operator changes a
  // dropdown. While present, the poller's manifest-driven hydration
  // skips the picker UI for that slot so a stale `variant_pack` or
  // `scene_pack` snapshot can't snap the dropdown back. Cleared on
  // full reset (clearPickerOverrides) but NOT on a fresh run, since
  // the operator's pick is what *drives* the new run.
  const pickerOverrides = new Set();

  rootEl.addEventListener("forge:tile-prompt-changed", (event) => {
    const { slotId, prompt } = event.detail;
    promptOverrides.set(slotId, prompt);
  });

  function _trackPickerChange(slotId) {
    pickerOverrides.add(slotId);
    // A picker change writes a new value into the textarea (option-c
    // rule). Treat it as a prompt override too so the next poll tick
    // doesn't overwrite the textarea with a stale manifest prompt.
    const tile = tilesById.get(slotId);
    if (tile) promptOverrides.set(slotId, tile.getPrompt());
  }

  rootEl.addEventListener("forge:tile-scene-changed", (event) => {
    _trackPickerChange(event.detail.slotId);
  });

  rootEl.addEventListener("forge:tile-variant-changed", (event) => {
    _trackPickerChange(event.detail.slotId);
  });

  rootEl.addEventListener("forge:tile-excluded-changed", async (event) => {
    const { slotId, excluded } = event.detail;
    const tile = tilesById.get(slotId);
    const runId = tile?.getRunId() ?? null;
    if (!runId) return; // Can't persist before a run exists.
    try {
      await patchSlot(runId, slotId, { excluded });
    } catch (error) {
      console.error("Slot patch failed:", error);
    }
  });

  rootEl.addEventListener("forge:tile-regen-requested", async (event) => {
    const { slotId, runId, prompt } = event.detail;
    const tile = tilesById.get(slotId);
    const pick = _pickForRegenerate(tile);
    try {
      await regenerateSlot(runId, slotId, prompt, pick);
      promptOverrides.set(slotId, prompt);
      // The page-level poller stops at terminal states; tell the app
      // shell to make sure it's running so the new image lands in the
      // tile without the operator having to refresh.
      window.dispatchEvent(
        new CustomEvent("forge:regen-queued", { detail: { runId } }),
      );
    } catch (error) {
      console.error("Regenerate failed:", error);
      window.dispatchEvent(
        new CustomEvent("forge:toast", {
          detail: { type: "error", message: error.message ?? String(error) },
        }),
      );
    }
  });

  function _pickForRegenerate(tile) {
    if (!tile) return null;
    const scenePick = tile.getScenePick?.();
    if (scenePick) return { scene: scenePick };
    const variantPick = tile.getVariantPick?.();
    if (variantPick) return { anchor_variant: variantPick };
    return null;
  }

  // ---- public API ------------------------------------------------------

  function setRunId(runId) {
    for (const tile of tilesById.values()) {
      tile.setRunId(runId);
    }
  }

  function applyManifest(manifest) {
    for (const [slotId, slotState] of Object.entries(manifest.slots)) {
      const tile = tilesById.get(slotId);
      if (!tile) continue;
      // Don't overwrite a textarea the user is currently editing —
      // including when the edit came from a picker change (we wrote
      // the new value into promptOverrides at that point so the
      // poller can't undo it on the next tick).
      const userOverride = promptOverrides.get(slotId);
      if (userOverride === undefined && slotState.prompt) {
        tile.setPrompt(slotState.prompt);
      }
      tile.update(slotState, {
        runId: manifest.run_id,
        skipPickerHydration: pickerOverrides.has(slotId),
      });
    }
  }

  function getPrompt(slotId) {
    const tile = tilesById.get(slotId);
    return tile ? tile.getPrompt() : null;
  }

  function getPickForSlot(slotId) {
    // Picker pick to send alongside a regenerate POST. Returns null
    // for slots without a picker (shouldn't happen — every tile has
    // one — but kept defensive). Source-panel uses this for the
    // batch-regenerate path so each queued regenerate carries the
    // tile's current dropdown snapshot.
    return _pickForRegenerate(tilesById.get(slotId));
  }

  function collectPromptOverrides() {
    // Caller (source-panel) reads this when posting POST /api/runs so
    // user-edited prompts ride along as `slot_overrides`.
    const overrides = {};
    for (const [slotId, tile] of tilesById.entries()) {
      const value = tile.getPrompt();
      if (value && value !== tile.slotDef.default_prompt) {
        overrides[slotId] = value;
      }
    }
    return overrides;
  }

  function getSelectedSlotIds() {
    const selected = [];
    for (const [slotId, tile] of tilesById.entries()) {
      if (tile.isSelected()) selected.push(slotId);
    }
    return selected;
  }

  function clearSelection() {
    for (const tile of tilesById.values()) {
      tile.setSelected(false);
    }
  }

  function resetVisuals() {
    // Wipe every tile back to its blank/pending appearance: drop the
    // image, hide the seed pill, clear errors, set status pill to
    // "pending". Used after a cancel so the gallery stops showing
    // half-rendered state from the cancelled run.
    for (const tile of tilesById.values()) {
      tile.update(
        { status: "pending", image: null, seed_used: null, error: null },
        { runId: null },
      );
      tile.setRunId(null);
    }
  }

  function clearPromptOverrides() {
    promptOverrides.clear();
  }

  function clearPickerOverrides() {
    pickerOverrides.clear();
  }

  function collectSceneSelections() {
    // Returns the 9 (pack, scene_id) picks from the scene tiles, in
    // slot order 17-25. Source panel posts these as
    // ``scene_selections`` on POST /api/runs.
    const picks = [];
    for (const order of SCENE_SLOT_INDICES) {
      const tile = tilesById.get(`scene_${order}`);
      const pick = tile?.getScenePick();
      if (pick) picks.push({ pack: pick.pack, scene_id: pick.scene_id });
    }
    return picks;
  }

  function collectAnchorVariants() {
    // Returns a map of anchor_slot_id -> {pack, variant_id} for every
    // anchor tile that has a pick. Posted as ``anchor_variants`` on
    // POST /api/runs. Anchors not in the map fall back to the default
    // pack's first variant for that slot (server side).
    const picks = {};
    for (const [slotId, tile] of tilesById.entries()) {
      if (slotId.startsWith("scene_")) continue;
      const pick = tile.getVariantPick?.();
      if (pick) picks[slotId] = { pack: pick.pack, variant_id: pick.variant_id };
    }
    return picks;
  }

  return {
    setRunId,
    applyManifest,
    getPrompt,
    getPickForSlot,
    collectPromptOverrides,
    clearPromptOverrides,
    clearPickerOverrides,
    collectSceneSelections,
    collectAnchorVariants,
    getSelectedSlotIds,
    clearSelection,
    resetVisuals,
  };
}
