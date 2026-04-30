// Left-column controls: source upload, params, trigger word, generate-all.

import { createRun, uploadSourceImage } from "./run-client.mjs";

export function createSourcePanel({ slotGrid, onRunStart }) {
  const $drop = document.getElementById("source-drop");
  const $file = document.getElementById("source-file");
  const $empty = document.getElementById("source-empty");
  const $preview = document.getElementById("source-preview");
  const $sourceImage = document.getElementById("source-image");
  const $sourceInfo = document.getElementById("source-info");

  const $trigger = document.getElementById("trigger-word");
  const $seed = document.getElementById("seed");
  const $steps = document.getElementById("steps");
  const $guidance = document.getElementById("guidance");

  const $generate = document.getElementById("generate-all");
  const $queueStatus = document.getElementById("queue-status");
  const $runError = document.getElementById("run-error");

  let _sourceId = null;
  let _busy = false;

  // ---- Drag-and-drop ---------------------------------------------------

  $drop.addEventListener("click", (event) => {
    // The label wraps both the input and the visible drop zone, so
    // clicks on the visible parts already trigger the input. Don't
    // double-fire if the click landed directly on the input.
    if (event.target === $file) return;
    $file.click();
  });

  $drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    $drop.classList.add("forge-source-drop--hover");
  });

  $drop.addEventListener("dragleave", () => {
    $drop.classList.remove("forge-source-drop--hover");
  });

  $drop.addEventListener("drop", async (event) => {
    event.preventDefault();
    $drop.classList.remove("forge-source-drop--hover");
    const file = event.dataTransfer?.files?.[0];
    if (file) await _uploadFile(file);
  });

  $file.addEventListener("change", async () => {
    const file = $file.files?.[0];
    if (file) await _uploadFile(file);
  });

  async function _uploadFile(file) {
    try {
      _setBusy(true, "Uploading source image…");
      const result = await uploadSourceImage(file);
      _sourceId = result.source_id;
      _showPreview(file, result);
      $generate.disabled = false;
      _clearError();
      _setBusy(false, "");
    } catch (error) {
      _setBusy(false, "");
      _showError(error.message ?? String(error));
    }
  }

  function _showPreview(file, result) {
    const objectUrl = URL.createObjectURL(file);
    $sourceImage.src = objectUrl;
    $sourceInfo.textContent = `${result.width}×${result.height} · source_id ${result.source_id}`;
    $empty.hidden = true;
    $preview.hidden = false;
  }

  // ---- Generate all ----------------------------------------------------

  $generate.addEventListener("click", async () => {
    if (!_sourceId || _busy) return;
    try {
      _setBusy(true, "Queuing run…");
      const slotOverrides = slotGrid.collectPromptOverrides();
      const result = await createRun({
        sourceId: _sourceId,
        triggerWord: $trigger.value.trim(),
        seed: Number($seed.value) || 1234,
        steps: Number($steps.value) || 28,
        guidance: Number($guidance.value) || 4.5,
        slotOverrides,
      });
      _setBusy(false, `Run ${result.run_id} queued.`);
      onRunStart(result.run_id);
    } catch (error) {
      _setBusy(false, "");
      _showError(error.message ?? String(error));
    }
  });

  // ---- Helpers ---------------------------------------------------------

  function _setBusy(busy, status) {
    _busy = busy;
    $generate.disabled = busy || !_sourceId;
    $queueStatus.textContent = status;
  }

  function _showError(message) {
    $runError.textContent = message;
    $runError.hidden = false;
  }

  function _clearError() {
    $runError.hidden = true;
    $runError.textContent = "";
  }

  function setRunStatus(manifest) {
    const stateEl = document.querySelector(".forge-run-state");
    const runIdEl = document.getElementById("forge-run-id");
    if (stateEl) {
      stateEl.dataset.state = manifest.status;
      stateEl.textContent = manifest.status;
    }
    if (runIdEl) runIdEl.textContent = manifest.run_id;

    if (manifest.status === "done") {
      $queueStatus.textContent = "Run complete.";
    } else if (manifest.status === "running") {
      const totalSlots = Object.keys(manifest.slots).length;
      const doneSlots = Object.values(manifest.slots).filter(
        (s) => s.status === "done",
      ).length;
      $queueStatus.textContent = `Generating… ${doneSlots} / ${totalSlots} slots done.`;
    } else if (manifest.status === "failed") {
      _showError(manifest.error ?? "Run failed.");
    }
  }

  return { setRunStatus };
}
