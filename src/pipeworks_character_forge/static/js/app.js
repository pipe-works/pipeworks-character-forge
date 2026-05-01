// PipeWorks Character Forge — frontend entry point.
//
// Boots on DOMContentLoaded:
//   1. Fetches /api/slots and builds the 26-tile grid.
//   2. Wires the source-upload + controls panel.
//   3. If a run id is stashed in localStorage, fetches that run's
//      manifest and re-paints the page so a refresh doesn't wipe work.
//   4. On "Generate all", starts a ProgressPoller and pipes manifest
//      updates into the grid + status panel until status reaches a
//      terminal state.

import { fetchRunManifest, fetchScenePacks, fetchSlotCatalog } from "./run-client.mjs";
import { ProgressPoller } from "./progress-bus.mjs";
import { createSlotGrid } from "./slot-grid.mjs";
import { createSourcePanel } from "./source-panel.mjs";
import { initThemeToggle } from "./theme-toggle.mjs";

const RUN_ID_STORAGE_KEY = "pipeworks-forge:current-run-id";
const TERMINAL_STATES = new Set(["done", "failed", "cancelled"]);

async function fetchHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

async function main() {
  initThemeToggle();

  // Header version chip (best-effort; harmless if /api/health is down).
  fetchHealth().then((health) => {
    const versionEl = document.getElementById("app-version");
    if (versionEl && health?.version) versionEl.textContent = `v${health.version}`;
  });

  let catalog;
  let scenePackResult;
  try {
    [catalog, scenePackResult] = await Promise.all([
      fetchSlotCatalog(),
      fetchScenePacks(),
    ]);
  } catch (error) {
    document.body.insertAdjacentHTML(
      "afterbegin",
      `<p class="forge-fatal">Failed to load slot data: ${error.message}</p>`,
    );
    return;
  }
  if (scenePackResult?.warnings?.length) {
    // Surface any pack-load warnings so the operator notices a busted
    // JSON file in their packs dir without having to read server logs.
    console.warn("Scene-pack warnings:", scenePackResult.warnings);
  }

  const slotGrid = createSlotGrid(
    document.getElementById("slot-grid"),
    catalog,
    scenePackResult,
  );

  let activePoller = null;

  function _startPoller(runId) {
    if (activePoller) activePoller.stop();
    activePoller = new ProgressPoller(runId);
    activePoller.start();
  }

  function _stopPoller() {
    if (activePoller) {
      activePoller.stop();
      activePoller = null;
    }
  }

  const sourcePanel = createSourcePanel({
    slotGrid,
    onRunStart(runId) {
      localStorage.setItem(RUN_ID_STORAGE_KEY, runId);
      slotGrid.setRunId(runId);
      _startPoller(runId);
    },
    onRunCancelled() {
      // Run reached `cancelled`: stop polling and reset every tile to
      // its blank state so the gallery doesn't keep showing half of
      // the cancelled run. PNGs stay on disk for inspection.
      _stopPoller();
      slotGrid.resetVisuals();
    },
  });

  window.addEventListener("forge:manifest", (event) => {
    const manifest = event.detail;
    slotGrid.applyManifest(manifest);
    sourcePanel.setRunStatus(manifest);
  });

  // A regenerate (single tile, batch, or cascade) was just queued. The
  // poller may have stopped at the previous run's terminal state, so
  // (re)start it — the new image only lands in the UI if we're polling.
  window.addEventListener("forge:regen-queued", (event) => {
    const runId = event.detail?.runId;
    if (!runId) return;
    _startPoller(runId);
  });

  window.addEventListener("forge:run-cleared", () => {
    localStorage.removeItem(RUN_ID_STORAGE_KEY);
    _stopPoller();
  });

  // Refresh-survival: if we shipped a run id last time, fetch its
  // manifest and re-paint everything. If the run is no longer on disk,
  // drop the stale id and boot clean.
  const storedRunId = localStorage.getItem(RUN_ID_STORAGE_KEY);
  if (storedRunId) {
    try {
      const manifest = await fetchRunManifest(storedRunId);
      sourcePanel.hydrateFromManifest(manifest);
      slotGrid.setRunId(manifest.run_id);
      window.dispatchEvent(new CustomEvent("forge:manifest", { detail: manifest }));
      if (!TERMINAL_STATES.has(manifest.status)) {
        _startPoller(manifest.run_id);
      }
    } catch (error) {
      console.warn("Stored run id no longer resolvable, clearing:", error);
      localStorage.removeItem(RUN_ID_STORAGE_KEY);
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
