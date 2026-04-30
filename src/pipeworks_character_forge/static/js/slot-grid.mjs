// Renders the 26-tile grid (stylized base + 25 leaves) and applies
// manifest updates from the progress poller.

import { regenerateSlot } from "./run-client.mjs";
import { createSlotTile } from "./slot-tile.mjs";

export function createSlotGrid(rootEl, catalog) {
  // Order is enforced by /api/slots: intermediate first, then leaves
  // sorted by `order`.
  const tilesById = new Map();

  // Promoted base tile.
  const baseTile = createSlotTile(catalog.intermediate, { promoted: true });
  tilesById.set(catalog.intermediate.id, baseTile);
  rootEl.appendChild(baseTile.root);

  // Leaves.
  for (const slotDef of catalog.slots) {
    const tile = createSlotTile(slotDef);
    tilesById.set(slotDef.id, tile);
    rootEl.appendChild(tile.root);
  }

  // ---- per-tile interaction --------------------------------------------

  // Track per-slot prompt overrides so a manifest update doesn't clobber
  // user edits made before the chain has caught up to that slot.
  const promptOverrides = new Map();

  rootEl.addEventListener("forge:tile-prompt-changed", (event) => {
    const { slotId, prompt } = event.detail;
    promptOverrides.set(slotId, prompt);
  });

  rootEl.addEventListener("forge:tile-regen-requested", async (event) => {
    const { slotId, runId, prompt } = event.detail;
    try {
      await regenerateSlot(runId, slotId, prompt);
      promptOverrides.set(slotId, prompt);
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

  return { setRunId, applyManifest, collectPromptOverrides };
}
