// Polls GET /api/runs/{runId} on a fixed interval and dispatches a
// `forge:manifest` CustomEvent on `window` whenever the manifest changes.
// Stops automatically when the run reaches a terminal state.

import { fetchRunManifest } from "./run-client.mjs";

const POLL_INTERVAL_MS = 2000;
// `cancelled` is terminal too — leaving it out kept the poller spinning
// forever after a cancel.
const TERMINAL_STATES = new Set(["done", "failed", "cancelled"]);

export class ProgressPoller {
  constructor(runId, { intervalMs = POLL_INTERVAL_MS } = {}) {
    this.runId = runId;
    this.intervalMs = intervalMs;
    this._timer = null;
    this._stopped = false;
  }

  start() {
    if (this._stopped) return;
    this._poll();
  }

  stop() {
    this._stopped = true;
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
  }

  async _poll() {
    if (this._stopped) return;
    try {
      const manifest = await fetchRunManifest(this.runId);
      window.dispatchEvent(
        new CustomEvent("forge:manifest", { detail: manifest }),
      );
      if (TERMINAL_STATES.has(manifest.status)) {
        this.stop();
        return;
      }
    } catch (error) {
      // Network blips happen during long runs — log and keep polling.
      console.warn("ProgressPoller: fetch failed, retrying", error);
    }
    this._timer = setTimeout(() => this._poll(), this.intervalMs);
  }
}
