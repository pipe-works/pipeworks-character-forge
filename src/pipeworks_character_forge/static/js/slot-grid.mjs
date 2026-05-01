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

export function createSlotGrid(rootEl, catalog, scenePackResult) {
  // Order is enforced by /api/slots: intermediate first, then anchors
  // sorted by `order`. Scene leaves come from /api/scene-packs and are
  // appended after the anchor tiles in positions 17-25.
  const tilesById = new Map();
  const scenePacks = scenePackResult?.packs ?? [];
  // The "default" pack is the no-selection fallback. Pre-pick its
  // first 9 scenes so a fresh page reads sensibly even if the operator
  // never touches the dropdowns. Loader guarantees default has >= 9
  // scenes (run-create errors loudly otherwise).
  const defaultPack = scenePacks.find((p) => p.name === "default");

  // Promoted base tile.
  const baseTile = createSlotTile(catalog.intermediate, { promoted: true });
  tilesById.set(catalog.intermediate.id, baseTile);
  rootEl.appendChild(baseTile.root);

  // Anchor leaves.
  for (const slotDef of catalog.slots) {
    const tile = createSlotTile(slotDef);
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

  rootEl.addEventListener("forge:tile-prompt-changed", (event) => {
    const { slotId, prompt } = event.detail;
    promptOverrides.set(slotId, prompt);
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
    try {
      await regenerateSlot(runId, slotId, prompt);
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
      // Don't overwrite a textarea the user is currently editing.
      const userOverride = promptOverrides.get(slotId);
      if (userOverride === undefined && slotState.prompt) {
        tile.setPrompt(slotState.prompt);
      }
      tile.update(slotState, { runId: manifest.run_id });
    }
  }

  function getPrompt(slotId) {
    const tile = tilesById.get(slotId);
    return tile ? tile.getPrompt() : null;
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

  return {
    setRunId,
    applyManifest,
    getPrompt,
    collectPromptOverrides,
    clearPromptOverrides,
    collectSceneSelections,
    getSelectedSlotIds,
    clearSelection,
    resetVisuals,
  };
}
