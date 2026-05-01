// Thin fetch wrappers around the Character Forge API surface.
// Throws a descriptive Error on non-2xx responses so callers can `await`
// without manually unpacking response.ok everywhere.

async function _readError(response) {
  try {
    const body = await response.json();
    if (body && body.detail) return body.detail;
    return JSON.stringify(body);
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function fetchSlotCatalog() {
  const response = await fetch("/api/slots");
  if (!response.ok) {
    throw new Error(`Failed to fetch slot catalog: ${await _readError(response)}`);
  }
  return response.json();
}

export async function uploadSourceImage(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/source-image", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Source upload failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function fetchScenePacks() {
  const response = await fetch("/api/scene-packs");
  if (!response.ok) {
    throw new Error(`Failed to fetch scene packs: ${await _readError(response)}`);
  }
  return response.json();
}

export async function fetchAnchorVariants() {
  const response = await fetch("/api/anchor-variants");
  if (!response.ok) {
    throw new Error(`Failed to fetch anchor variants: ${await _readError(response)}`);
  }
  return response.json();
}

export async function createRun({
  sourceId,
  triggerWord,
  stylePrefix,
  styleSuffix,
  seed,
  steps,
  guidance,
  slotOverrides,
  onlySlots,
  sceneSelections,
  anchorVariants,
}) {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source_id: sourceId,
      trigger_word: triggerWord || null,
      style_prefix: stylePrefix || null,
      style_suffix: styleSuffix || null,
      seed,
      steps,
      guidance,
      slot_overrides: slotOverrides || {},
      only_slots: onlySlots || null,
      scene_selections: sceneSelections || null,
      anchor_variants: anchorVariants || null,
    }),
  });
  if (!response.ok) {
    throw new Error(`Run create failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function cascadeRun(runId) {
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/cascade`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(`Cascade failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function cancelRun(runId) {
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(`Cancel failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function exportDataset(runId) {
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/dataset`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(`Dataset export failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function fetchRunManifest(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`Run fetch failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function patchSlot(runId, slotId, patch) {
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/slots/${encodeURIComponent(slotId)}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  if (!response.ok) {
    throw new Error(`Slot patch failed: ${await _readError(response)}`);
  }
  return response.json();
}

export async function regenerateSlot(runId, slotId, prompt) {
  const body = prompt !== undefined && prompt !== null ? { prompt } : {};
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/slots/${encodeURIComponent(slotId)}/regenerate`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    throw new Error(`Regenerate failed: ${await _readError(response)}`);
  }
  return response.json();
}

export function imageUrlFor(runId, filename) {
  return `/runs/${encodeURIComponent(runId)}/${encodeURIComponent(filename)}`;
}
