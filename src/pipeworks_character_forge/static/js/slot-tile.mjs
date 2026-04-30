// One slot tile. Built from a SlotDef from /api/slots; `update(slotState)`
// applies a per-slot row from the run manifest. Emits two custom events
// when the user interacts with the tile:
//
//   forge:tile-prompt-changed { slotId, prompt }   — debounced textarea
//   forge:tile-regen-requested { slotId, prompt }  — regenerate click
//
// The grid (slot-grid.mjs) listens for both and decides what to do
// (persist locally as overrides, or POST a regenerate request).

import { imageUrlFor } from "./run-client.mjs";

const STATUS_LABELS = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  failed: "Failed",
};

const PROMPT_CHANGE_DEBOUNCE_MS = 250;

function _orderBadge(order) {
  return String(order).padStart(2, "0");
}

export function createSlotTile(slotDef, { promoted = false } = {}) {
  const root = document.createElement("article");
  root.className = "forge-tile";
  root.dataset.slotId = slotDef.id;
  root.dataset.group = slotDef.group;
  if (promoted) root.classList.add("forge-tile--promoted");

  root.innerHTML = `
    <header class="forge-tile__head">
      <span class="forge-tile__order">${_orderBadge(slotDef.order)}</span>
      <h3 class="forge-tile__label">${slotDef.label}</h3>
      <span class="forge-tile__status" data-status="pending">${STATUS_LABELS.pending}</span>
    </header>
    <figure class="forge-tile__media">
      <div class="forge-tile__skeleton" aria-hidden="true"></div>
      <img class="forge-tile__image" hidden alt="${slotDef.label}" />
    </figure>
    <div class="forge-tile__body">
      <textarea
        class="forge-tile__prompt"
        rows="3"
        spellcheck="false">${slotDef.default_prompt}</textarea>
      <div class="forge-tile__actions">
        <button type="button" class="forge-btn forge-btn--small forge-tile__regen" disabled>
          Regenerate
        </button>
        <span class="forge-tile__seed" hidden></span>
      </div>
      <p class="forge-tile__error" hidden></p>
    </div>
  `;

  const $statusPill = root.querySelector(".forge-tile__status");
  const $skeleton = root.querySelector(".forge-tile__skeleton");
  const $image = root.querySelector(".forge-tile__image");
  const $prompt = root.querySelector(".forge-tile__prompt");
  const $regen = root.querySelector(".forge-tile__regen");
  const $seed = root.querySelector(".forge-tile__seed");
  const $error = root.querySelector(".forge-tile__error");

  let _runId = null;
  let _debounceTimer = null;

  function _emit(name, detail) {
    root.dispatchEvent(
      new CustomEvent(name, { bubbles: true, composed: true, detail }),
    );
  }

  $prompt.addEventListener("input", () => {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      _emit("forge:tile-prompt-changed", {
        slotId: slotDef.id,
        prompt: $prompt.value,
      });
    }, PROMPT_CHANGE_DEBOUNCE_MS);
  });

  $regen.addEventListener("click", () => {
    if (!_runId) return;
    _emit("forge:tile-regen-requested", {
      slotId: slotDef.id,
      runId: _runId,
      prompt: $prompt.value,
    });
  });

  function update(slotState, { runId } = {}) {
    if (runId) _runId = runId;

    const status = slotState?.status ?? "pending";
    $statusPill.dataset.status = status;
    $statusPill.textContent = STATUS_LABELS[status] ?? status;

    if (slotState?.image && _runId) {
      const url = imageUrlFor(_runId, slotState.image);
      // Cache-bust on regen so the browser fetches the fresh PNG.
      const cacheBust = slotState.regen_count
        ? `?v=${slotState.regen_count}`
        : "";
      $image.src = url + cacheBust;
      $image.hidden = false;
      $skeleton.hidden = true;
    } else {
      $image.hidden = true;
      $skeleton.hidden = false;
    }

    if (slotState?.seed_used !== undefined && slotState.seed_used !== null) {
      $seed.textContent = `seed ${slotState.seed_used}`;
      $seed.hidden = false;
    }

    if (slotState?.error) {
      $error.textContent = slotState.error;
      $error.hidden = false;
    } else {
      $error.hidden = true;
    }

    // Regenerate is only possible once a run exists.
    $regen.disabled = !_runId;
  }

  function setRunId(runId) {
    _runId = runId;
    $regen.disabled = !runId;
  }

  function getPrompt() {
    return $prompt.value;
  }

  function setPrompt(prompt) {
    $prompt.value = prompt;
  }

  return { root, update, setRunId, getPrompt, setPrompt, slotDef };
}
