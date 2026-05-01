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

export function createSlotTile(
  slotDef,
  { promoted = false, scenePicker = null, anchorVariantPicker = null } = {},
) {
  const root = document.createElement("article");
  root.className = "forge-tile";
  root.dataset.slotId = slotDef.id;
  root.dataset.group = slotDef.group;
  if (promoted) root.classList.add("forge-tile--promoted");
  if (scenePicker) root.classList.add("forge-tile--scene");
  if (anchorVariantPicker) root.classList.add("forge-tile--variant");

  // Stylized base is excluded from the dataset by definition (it's an
  // intermediate, not training material), so its include checkbox is
  // hidden — there's nothing meaningful to toggle.
  const isIntermediate = slotDef.group === "intermediate";

  // Scene tiles get a <select> above the textarea so the operator can
  // swap which scene fills the slot. Anchor tiles get a parallel
  // <select> sourced from anchor-variant packs covering this anchor;
  // both render the same shell, never both at once.
  let pickerHtml = "";
  if (scenePicker) {
    pickerHtml = `<select class="forge-tile__scene-picker" title="Pick a scene for this slot">
         ${_renderSceneOptions(scenePicker.packs, scenePicker.initial)}
       </select>`;
  } else if (anchorVariantPicker) {
    pickerHtml = `<select class="forge-tile__variant-picker" title="Pick a phrasing variant for this anchor">
         ${_renderAnchorVariantOptions(
           anchorVariantPicker.packs,
           slotDef.id,
           anchorVariantPicker.initial,
         )}
       </select>`;
  }

  root.innerHTML = `
    <header class="forge-tile__head">
      <input
        type="checkbox"
        class="forge-tile__select"
        title="Tick to generate (or regenerate) only this slot"
        aria-label="Select this slot"
      />
      <span class="forge-tile__order">${_orderBadge(slotDef.order)}</span>
      <h3 class="forge-tile__label">${_escape(slotDef.label)}</h3>
      <span class="forge-tile__status" data-status="pending">${STATUS_LABELS.pending}</span>
    </header>
    <figure class="forge-tile__media">
      <div class="forge-tile__skeleton" aria-hidden="true"></div>
      <img class="forge-tile__image" hidden alt="${_escape(slotDef.label)}" />
    </figure>
    <div class="forge-tile__body">
      ${pickerHtml}
      <textarea
        class="forge-tile__prompt"
        rows="3"
        spellcheck="false">${_escape(slotDef.default_prompt)}</textarea>
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

  const $label = root.querySelector(".forge-tile__label");
  const $statusPill = root.querySelector(".forge-tile__status");
  const $skeleton = root.querySelector(".forge-tile__skeleton");
  const $image = root.querySelector(".forge-tile__image");
  const $prompt = root.querySelector(".forge-tile__prompt");
  const $regen = root.querySelector(".forge-tile__regen");
  const $select = root.querySelector(".forge-tile__select");
  const $include = root.querySelector(".forge-tile__include-checkbox");
  const $seed = root.querySelector(".forge-tile__seed");
  const $error = root.querySelector(".forge-tile__error");
  const $scenePicker = root.querySelector(".forge-tile__scene-picker");
  const $variantPicker = root.querySelector(".forge-tile__variant-picker");

  let _runId = null;
  let _debounceTimer = null;
  // For scene tiles, _scenePick is the currently-selected (pack,
  // scene_id) and _sceneDefaultPrompt is the prompt the picker filled
  // into the textarea last (used to honor the option-c rule: only
  // overwrite the textarea on a new pick if the operator hasn't edited
  // away from the previous scene's default).
  let _scenePick = scenePicker ? { ...scenePicker.initial } : null;
  let _sceneDefaultPrompt = scenePicker ? slotDef.default_prompt : null;
  // Mirror state for anchor-variant tiles. Same option-c rule: the
  // textarea only updates when it still matches the prompt the picker
  // filled in last.
  let _variantPick = anchorVariantPicker ? { ...anchorVariantPicker.initial } : null;
  let _variantDefaultPrompt = anchorVariantPicker ? slotDef.default_prompt : null;

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

  if ($variantPicker) {
    $variantPicker.addEventListener("change", () => {
      const value = $variantPicker.value; // "pack__variant_id"
      const [packName, variantId] = value.split("__");
      const variant = _findAnchorVariant(
        anchorVariantPicker.packs,
        packName,
        slotDef.id,
        variantId,
      );
      if (!variant) return;
      _variantPick = { pack: packName, variant_id: variantId };
      // Same option-c rule as scenes — operator hand-edits win.
      if ($prompt.value === _variantDefaultPrompt) {
        $prompt.value = variant.prompt;
      }
      _variantDefaultPrompt = variant.prompt;
      _emit("forge:tile-variant-changed", {
        slotId: slotDef.id,
        pack: packName,
        variantId,
      });
    });
  }

  if ($scenePicker) {
    $scenePicker.addEventListener("change", () => {
      const value = $scenePicker.value; // "pack__scene_id"
      const [packName, sceneId] = value.split("__");
      const scene = _findScene(scenePicker.packs, packName, sceneId);
      if (!scene) return;
      _scenePick = { pack: packName, scene_id: sceneId };
      $label.textContent = scene.label;
      // Option-c rule from the design: only overwrite the textarea if
      // it still matches what the picker filled in last. Operator edits
      // win — they're not surprised by a dropdown change wiping their
      // tweaks.
      if ($prompt.value === _sceneDefaultPrompt) {
        $prompt.value = scene.default_prompt;
      }
      _sceneDefaultPrompt = scene.default_prompt;
      _emit("forge:tile-scene-changed", {
        slotId: slotDef.id,
        pack: packName,
        sceneId,
        label: scene.label,
      });
    });
  }

  function update(slotState, { runId } = {}) {
    if (runId) _runId = runId;

    // Hydrate scene metadata from the manifest. The picker dropdown is
    // updated to reflect the resolved (pack, scene_id) so a refreshed
    // page reads truthfully even if the manifest was created on a
    // different machine with different defaults.
    if ($scenePicker && slotState?.scene_pack && slotState?.scene_id) {
      const value = `${slotState.scene_pack}__${slotState.scene_id}`;
      if ($scenePicker.value !== value) $scenePicker.value = value;
      _scenePick = { pack: slotState.scene_pack, scene_id: slotState.scene_id };
      if (slotState.scene_label) $label.textContent = slotState.scene_label;
    }

    // Hydrate anchor-variant snapshot from the manifest. Same shape as
    // scene hydration. The label stays whatever the catalog/slot says
    // — variants describe the *phrasing*, not the shot.
    if ($variantPicker && slotState?.variant_pack && slotState?.variant_id) {
      const value = `${slotState.variant_pack}__${slotState.variant_id}`;
      if ($variantPicker.value !== value) $variantPicker.value = value;
      _variantPick = {
        pack: slotState.variant_pack,
        variant_id: slotState.variant_id,
      };
    }

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
    // Selection survives across run boundaries — operator can pick
    // slots before any run exists (selective initial generation) AND
    // after one finishes (batch regen). Just untick on cancel-reset
    // so the gallery doesn't carry stale selection into a fresh page.
    if (!runId) {
      $select.checked = false;
      root.classList.remove("forge-tile--selected");
    }
  }

  function getPrompt() {
    return $prompt.value;
  }

  function setPrompt(prompt) {
    $prompt.value = prompt;
  }

  function getScenePick() {
    return _scenePick ? { ...(_scenePick) } : null;
  }

  function getVariantPick() {
    return _variantPick ? { ...(_variantPick) } : null;
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
    getScenePick,
    getVariantPick,
    isSelected,
    setSelected,
    slotDef,
  };
}

function _renderSceneOptions(packs, initial) {
  // <optgroup> per pack so the operator can see what's coming from
  // where. The selected value is "<pack>__<scene_id>" — split by the
  // change handler. Pack/scene names are alphanumeric+underscore by
  // schema, but we still HTML-escape labels because they're free-form.
  return packs
    .map((pack) => {
      const options = pack.scenes
        .map((scene) => {
          const value = `${pack.name}__${scene.id}`;
          const selected =
            initial && pack.name === initial.pack && scene.id === initial.scene_id
              ? " selected"
              : "";
          return `<option value="${_escape(value)}"${selected}>${_escape(scene.label)}</option>`;
        })
        .join("");
      return `<optgroup label="${_escape(pack.label)}">${options}</optgroup>`;
    })
    .join("");
}

function _renderAnchorVariantOptions(packs, slotId, initial) {
  // <optgroup> per pack covering this slot. Sparse packs that don't
  // cover ``slotId`` are skipped — operator only sees relevant
  // alternatives. The selected value is "<pack>__<variant_id>".
  return packs
    .filter((pack) => Array.isArray(pack.variants?.[slotId]) && pack.variants[slotId].length > 0)
    .map((pack) => {
      const options = pack.variants[slotId]
        .map((variant) => {
          const value = `${pack.name}__${variant.id}`;
          const selected =
            initial && pack.name === initial.pack && variant.id === initial.variant_id
              ? " selected"
              : "";
          return `<option value="${_escape(value)}"${selected}>${_escape(variant.label)}</option>`;
        })
        .join("");
      return `<optgroup label="${_escape(pack.label)}">${options}</optgroup>`;
    })
    .join("");
}

function _findAnchorVariant(packs, packName, slotId, variantId) {
  for (const pack of packs) {
    if (pack.name !== packName) continue;
    const slotVariants = pack.variants?.[slotId];
    if (!Array.isArray(slotVariants)) return null;
    return slotVariants.find((v) => v.id === variantId) ?? null;
  }
  return null;
}

function _findScene(packs, packName, sceneId) {
  for (const pack of packs) {
    if (pack.name !== packName) continue;
    return pack.scenes.find((s) => s.id === sceneId) ?? null;
  }
  return null;
}

function _escape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
