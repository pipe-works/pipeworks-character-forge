# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Light/dark theme toggle in the app header. Persists to
  `localStorage` under the `pw-theme` key, matching
  `pipeworks-image-generator`'s convention so a user's preference
  follows them across the PipeWorks app suite. Default is dark.
- App-shell layout (`.app-header`, `.app-main`, `.status-bar`)
  consumed verbatim from `pipe-works-base.css`. Header now carries
  the brand mark, instrument subtitle, version chip, run-state
  badge, run-id, and the theme toggle. Status bar at the bottom
  shows the current run progress.
- Version chip in the header — best-effort `GET /api/health` on
  load, so the build that's actually serving you is visible at a
  glance.
- `pw-forge make-dataset <run-id>` console subcommand. Copies the 25
  leaf `NN_<slot>.png` + `NN_<slot>.txt` pairs from a completed run
  into `<run-dir>/dataset/` (excluding `source.png`, `manifest.json`,
  and the intermediate `00_stylized_base.*`) so ai-toolkit can read
  the directory directly. Supports `--output-dir` to redirect, and
  `--force` to overwrite an existing dataset folder. Refuses with a
  non-zero exit code if the run is unknown, incomplete, or the target
  exists without `--force`. Warns on stderr when `trigger_word` is
  empty so the operator knows captions will not carry a LoRA prefix.
- `pw-forge` is now an argparse dispatch with two subcommands:
  `serve` (default — runs the FastAPI server, so the systemd
  `ExecStart=pw-forge` keeps working unchanged) and `make-dataset`.
- Frontend: vanilla ES modules + plain HTML, no build step. Left
  panel handles source upload + run params + trigger word + the
  Generate-all button; main pane is the 26-tile gallery (promoted
  stylized base + 25 leaves) with per-tile prompt editing and a
  Regenerate button. Tiles update from a `ProgressPoller` that polls
  `GET /api/runs/{id}` every 2 s and dispatches `forge:manifest`
  CustomEvents to the grid + status panel.
- Imports the shared `pipe-works-base.css` design tokens + Crimson
  Text / Courier Prime font set used across the PipeWorks app
  ecosystem; `forge.css` only contains layout-specific rules.
- 25-slot pipeline orchestrator (`api/services/pipeline_orchestrator.py`):
  stylized base first, then each leaf branches off it in display order;
  every i2i call gets a deterministic seed of
  `run_seed + slot_order + 1000 * regen_count` so reruns are
  reproducible and per-tile regenerates never collide.
- Disk-backed run registry (`api/services/run_store.py`) — one dir per
  run, atomic `manifest.json` writes via tmp + `os.replace`, schema
  versioned for future migrations.
- Single-worker FIFO job queue (`api/services/job_queue.py`) wrapping
  the orchestrator so the GPU is never multiplexed.
- `POST /api/runs` creates a run and enqueues a full-chain job;
  `GET /api/runs[/{run_id}]` returns the manifest for polling;
  `POST /api/runs/{run_id}/slots/{slot_id}/regenerate` re-runs one slot
  with an optional prompt override.
- `/runs` static mount serves generated images at
  `/runs/<run_id>/NN_<slot>.png` for the frontend to compose URLs
  against.
- Captions written as `NN_<slot>.txt` next to each leaf image; trigger
  word is prepended when set.
- End-to-end nginx proxy check in `deploy/install.sh`: after the
  backend responds, the script also probes
  `https://forge.pipeworks.luminal.local/api/health` via
  `curl --resolve` to confirm cert + vhost + upstream wiring.
- `AGENTS.md` documents `/opt/python/3.12.13/bin/python3.12` as the
  canonical interpreter for venvs on Luminal and the
  `pipeworks:pipeworks` ownership convention.
- Repo skeleton: pyproject.toml pinned to Python 3.12, src-layout package
  `pipeworks_character_forge`, FastAPI shell with `/api/health`,
  `/api/slots`, and a placeholder `/` index page.
- Canonical 25-slot definition at
  `src/pipeworks_character_forge/data/slots.json` with default prompts
  for every slot.
- Slot catalog service exposing `list_slots()` / `get(slot_id)`.
- Pydantic-settings configuration class `PipeworksForgeConfig`.
- Deploy plumbing under `deploy/`: systemd unit, nginx vhost for
  `forge.pipeworks.luminal.local`, env example.
- Unit tests covering slot-catalog loading and uniqueness invariants.

### Changed

- `forge.css` rewritten on top of `pipe-works-base.css` design tokens
  (`--col-*`, `--font-*`, `--sp-*`, `--radius-*`, `--text-*`).
  Previously it shipped a parallel set of `--color-*` variables that
  ignored the design system and hard-coded the dark palette.

### Fixed

- Backend port moved 8410 → **8420** to dodge a collision with
  `pipeworks-pipeworks-org-author.service`, which is hard-coded to
  `--port 8410` and was claiming the socket whenever character-forge
  was restarting. Symptom on the operator side was nginx proxying to
  the author service whenever forge crashed, plus a permanent
  `address already in use` on systemd start. Updated:
  `core/config.py` default, `deploy/env/character-forge.env.example`,
  `deploy/nginx/forge.pipeworks.luminal.local`, `deploy/install.sh`
  pre-flight `PORT`. Operators on existing deploys must additionally
  edit the live `/etc/pipeworks/character-forge/character-forge.env`
  to set `PIPEWORKS_FORGE_SERVER_PORT=8420` since `install.sh` does
  not rewrite an existing env file.
- `deploy/install.sh` health probe now hits the backend over plain HTTP
  (`http://127.0.0.1:8420/api/health`) — previously used `https://`
  which always failed because nginx terminates TLS upstream of the
  backend.
- `deploy/install.sh` pre-flight now exec's the venv's python as the
  `pipeworks` systemd user. Catches the pyenv-private-home trap
  (`status=203/EXEC`) before cert + nginx + systemd are touched and
  prints a rebuild recipe pointing at `/opt/python/3.12.13`.
