// PipeWorks Character Forge — frontend entry point.
//
// Boots on DOMContentLoaded:
//   1. Fetches /api/slots and builds the 26-tile grid.
//   2. Wires the source-upload + controls panel.
//   3. On "Generate all", starts a ProgressPoller and pipes manifest
//      updates into the grid + status panel until status=done|failed.

import { fetchSlotCatalog } from "./run-client.mjs";
import { ProgressPoller } from "./progress-bus.mjs";
import { createSlotGrid } from "./slot-grid.mjs";
import { createSourcePanel } from "./source-panel.mjs";

async function main() {
  let catalog;
  try {
    catalog = await fetchSlotCatalog();
  } catch (error) {
    document.body.insertAdjacentHTML(
      "afterbegin",
      `<p class="forge-fatal">Failed to load slot catalog: ${error.message}</p>`,
    );
    return;
  }

  const slotGrid = createSlotGrid(
    document.getElementById("slot-grid"),
    catalog,
  );

  let activePoller = null;

  const sourcePanel = createSourcePanel({
    slotGrid,
    onRunStart(runId) {
      slotGrid.setRunId(runId);
      if (activePoller) activePoller.stop();
      activePoller = new ProgressPoller(runId);
      activePoller.start();
    },
  });

  window.addEventListener("forge:manifest", (event) => {
    const manifest = event.detail;
    slotGrid.applyManifest(manifest);
    sourcePanel.setRunStatus(manifest);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
