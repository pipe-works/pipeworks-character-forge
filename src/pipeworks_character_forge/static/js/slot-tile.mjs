// One slot tile. Built from a SlotDef from /api/slots; `update(slotState)`
// applies a per-slot row from the run manifest. Emits three custom events
// when the user interacts with the tile:
//
//   forge:tile-prompt-changed { slotId, prompt }     — debounced textarea
//   forge:tile-regen-requested { slotId, prompt }    — regenerate click
//   forge:tile-excluded-changed { slotId, excluded } — include checkbox
//
// The grid (slot-grid.mjs) listens for all three and decides what to do
// (persist locally as overrides, POST a regenerate, or PATCH the slot).

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

  // Stylized base is excluded from the dataset by definition (it's an
  // intermediate, not training material), so its include checkbox is
  // hidden — there's nothing meaningful to toggle.
  const isIntermediate = slotDef.group === "intermediate";

  root.innerHTML = `
    <header class="forge-tile__head">
      <input
        type="checkbox"
        class="forge-tile__select"
        title="Select this slot for batch regenerate"
        aria-label="Select for batch regenerate"
      />
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
        <label class="forge-tile__include" ${isIntermediate ? "hidden" : ""}>
          <input type="checkbox" class="forge-tile__include-checkbox" checked />
          <span>Include</span>
        </label>
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
  const $select = root.querySelector(".forge-tile__select");
  const $include = root.querySelector(".forge-tile__include-checkbox");
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

  if ($include) {
    $include.addEventListener("change", () => {
      _emit("forge:tile-excluded-changed", {
        slotId: slotDef.id,
        excluded: !$include.checked,
      });
      root.classList.toggle("forge-tile--excluded", !$include.checked);
    });
  }

  $select.addEventListener("change", () => {
    root.classList.toggle("forge-tile--selected", $select.checked);
    _emit("forge:tile-selection-changed", {
      slotId: slotDef.id,
      selected: $select.checked,
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

    // Sync the Include checkbox with the manifest's excluded flag,
    // without firing a change event back at the server.
    if ($include && slotState && "excluded" in slotState) {
      const shouldBeChecked = !slotState.excluded;
      if ($include.checked !== shouldBeChecked) {
        $include.checked = shouldBeChecked;
      }
      root.classList.toggle("forge-tile--excluded", Boolean(slotState.excluded));
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

  function getRunId() {
    return _runId;
  }

  function isSelected() {
    return $select.checked;
  }

  function setSelected(selected) {
    if ($select.checked === selected) return;
    $select.checked = selected;
    root.classList.toggle("forge-tile--selected", selected);
  }

  return {
    root,
    update,
    setRunId,
    getRunId,
    getPrompt,
    setPrompt,
    isSelected,
    setSelected,
    slotDef,
  };
}
