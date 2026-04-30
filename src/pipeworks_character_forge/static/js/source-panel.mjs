// Left-column controls: source upload, params, trigger word, generate-all.

import {
  cancelRun,
  cascadeRun,
  createRun,
  exportDataset,
  regenerateSlot,
  uploadSourceImage,
} from "./run-client.mjs";

export function createSourcePanel({ slotGrid, onRunStart, onRunCancelled }) {
  const $drop = document.getElementById("source-drop");
  const $file = document.getElementById("source-file");
  const $empty = document.getElementById("source-empty");
  const $preview = document.getElementById("source-preview");
  const $sourceImage = document.getElementById("source-image");
  const $sourceInfo = document.getElementById("source-info");

  const $trigger = document.getElementById("trigger-word");
  const $stylePrefix = document.getElementById("style-prefix");
  const $seed = document.getElementById("seed");
  const $steps = document.getElementById("steps");
  const $guidance = document.getElementById("guidance");

  const $generate = document.getElementById("generate-all");
  const $cancel = document.getElementById("cancel-run");
  const $createDataset = document.getElementById("create-dataset");
  const $queueStatus = document.getElementById("queue-status");
  const $runError = document.getElementById("run-error");

  let _sourceId = null;
  let _runId = null;
  let _busy = false;
  let _selectedSlotIds = [];

  // ---- Drag-and-drop ---------------------------------------------------
  //
  // The drop zone is a <label> wrapping the hidden <input type="file">,
  // so clicks anywhere inside it forward to the input automatically.
  // No JS click handler needed — adding one fires the dialog twice.

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
    if (_busy) return;
    // Three flows depending on (run-exists, selection):
    //   no run + selection      → selective initial generation
    //                             (creates a run that runs base + only
    //                             selected leaves; ~52s × N+1 instead
    //                             of ~25 min full chain)
    //   existing run + selection → batch regenerate the selected slots
    //   no selection            → full chain (always a fresh run)
    if (_selectedSlotIds.length > 0 && _runId) {
      await _runBatchRegenerate();
      return;
    }
    if (!_sourceId) return;
    await _createRunFromInputs();
  });

  async function _createRunFromInputs() {
    try {
      // If the operator ticked tiles before any run, pass them as
      // only_slots so the orchestrator skips the rest. Stylized_base
      // ticks are stripped server-side because base always runs.
      const onlySlots = _selectedSlotIds.filter((id) => id !== "stylized_base");
      const isSelective = onlySlots.length > 0;
      _setBusy(true, isSelective ? `Queuing selective run (${onlySlots.length})…` : "Queuing run…");
      const slotOverrides = slotGrid.collectPromptOverrides();
      const result = await createRun({
        sourceId: _sourceId,
        triggerWord: $trigger.value.trim(),
        stylePrefix: $stylePrefix.value.trim(),
        seed: Number($seed.value) || 1234,
        steps: Number($steps.value) || 28,
        guidance: Number($guidance.value) || 4.5,
        slotOverrides,
        onlySlots: isSelective ? onlySlots : null,
      });
      _setBusy(false, `Run ${result.run_id} queued.`);
      _runId = result.run_id;
      $createDataset.disabled = true;
      onRunStart(result.run_id);
      // Selection has done its job — clear it so subsequent clicks
      // operate on the fresh run rather than re-running the same set.
      slotGrid.clearSelection();
      _selectedSlotIds = [];
      _refreshGenerateButtonLabel();
    } catch (error) {
      _setBusy(false, "");
      _showError(error.message ?? String(error));
    }
  }

  // ---- Batch regenerate ------------------------------------------------

  async function _runBatchRegenerate() {
    const onlyBase =
      _selectedSlotIds.length === 1 && _selectedSlotIds[0] === "stylized_base";

    if (onlyBase) {
      // Stylized base alone: ask about cascading. The base feeds every
      // leaf, so regenerating it without cascading leaves the existing
      // leaves referencing the previous base — usually not what the
      // operator wants.
      const choice = window.confirm(
        "You selected only the stylized base.\n\n" +
          "OK = Cascade — re-run the base AND all 25 leaves so everything " +
          "stays consistent.\n" +
          "Cancel = Just the base — the existing leaves will continue to " +
          "reference the OLD base on disk.",
      );
      try {
        _setBusy(true, choice ? "Cascading run…" : "Regenerating base…");
        if (choice) {
          await cascadeRun(_runId);
        } else {
          await regenerateSlot(_runId, "stylized_base");
        }
        _setBusy(false, choice ? "Cascade queued." : "Base regenerate queued.");
        slotGrid.clearSelection();
        $createDataset.disabled = true;
      } catch (error) {
        _setBusy(false, "");
        _showError(error.message ?? String(error));
      }
      return;
    }

    // ≥1 slot, possibly including base + leaves. Queue them in display
    // order; the backend FIFO worker dispatches one at a time.
    try {
      _setBusy(true, `Queuing ${_selectedSlotIds.length} regenerate(s)…`);
      for (const slotId of _selectedSlotIds) {
        await regenerateSlot(_runId, slotId);
      }
      _setBusy(false, `${_selectedSlotIds.length} regenerate(s) queued.`);
      slotGrid.clearSelection();
      $createDataset.disabled = true;
    } catch (error) {
      _setBusy(false, "");
      _showError(error.message ?? String(error));
    }
  }

  // Tile selection events bubble to the document; stash the latest
  // selection set so the Generate button can flip mode without
  // re-querying the DOM on every click.
  document.addEventListener("forge:tile-selection-changed", () => {
    _selectedSlotIds = slotGrid.getSelectedSlotIds();
    _refreshGenerateButtonLabel();
  });

  function _refreshGenerateButtonLabel() {
    const n = _selectedSlotIds.length;
    if (n === 0) {
      $generate.textContent = "Generate all 25";
      $generate.disabled = _busy || !_sourceId;
      return;
    }
    if (_runId) {
      // Existing run + selection → batch regenerate.
      $generate.textContent = `Regenerate selected (${n})`;
      $generate.disabled = _busy;
    } else {
      // Fresh page + selection → selective initial generation.
      // Counts include stylized_base if ticked (it always runs).
      const leafCount = _selectedSlotIds.filter((id) => id !== "stylized_base").length;
      $generate.textContent = `Generate selected (${leafCount})`;
      $generate.disabled = _busy || !_sourceId;
    }
  }

  // ---- Cancel run ------------------------------------------------------

  $cancel.addEventListener("click", async () => {
    if (!_runId || $cancel.disabled) return;
    $cancel.disabled = true;
    $cancel.textContent = "Cancelling…";
    try {
      await cancelRun(_runId);
      $queueStatus.textContent = "Cancel requested. Run stops after the current slot.";
    } catch (error) {
      _showError(error.message ?? String(error));
      $cancel.disabled = false;
      $cancel.textContent = "Cancel run";
    }
  });

  // ---- Create dataset --------------------------------------------------

  $createDataset.addEventListener("click", async () => {
    if (!_runId || $createDataset.disabled) return;
    const originalLabel = $createDataset.textContent;
    $createDataset.disabled = true;
    $createDataset.textContent = "Exporting…";
    try {
      const result = await exportDataset(_runId);
      $queueStatus.textContent = `Dataset written → ${result.path} (${result.pairs} pairs)`;
      $createDataset.textContent = "Dataset created ✓";
      window.setTimeout(() => {
        $createDataset.textContent = originalLabel;
        $createDataset.disabled = false;
      }, 3000);
    } catch (error) {
      _showError(error.message ?? String(error));
      $createDataset.textContent = originalLabel;
      $createDataset.disabled = false;
    }
  });

  // ---- Helpers ---------------------------------------------------------

  function _setBusy(busy, status) {
    _busy = busy;
    _refreshGenerateButtonLabel();
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

    // Cancel button is visible+enabled iff the run is actively running.
    const isRunning = manifest.status === "running";
    $cancel.hidden = !isRunning;
    $cancel.disabled = !isRunning || manifest.cancel_requested === true;
    if (!isRunning || manifest.cancel_requested !== true) {
      $cancel.textContent = "Cancel run";
    }

    if (manifest.status === "done") {
      $queueStatus.textContent = "Run complete.";
      $createDataset.disabled = false;
    } else if (manifest.status === "running") {
      const totalSlots = Object.keys(manifest.slots).length;
      const doneSlots = Object.values(manifest.slots).filter(
        (s) => s.status === "done",
      ).length;
      const tail = manifest.cancel_requested ? " (cancel pending)" : "";
      $queueStatus.textContent = `Generating… ${doneSlots} / ${totalSlots} slots done.${tail}`;
    } else if (manifest.status === "failed") {
      _showError(manifest.error ?? "Run failed.");
    } else if (manifest.status === "cancelled") {
      $queueStatus.textContent = "Run cancelled. Partial outputs preserved on disk.";
      onRunCancelled?.(manifest.run_id);
    }
  }

  return { setRunStatus };
}
