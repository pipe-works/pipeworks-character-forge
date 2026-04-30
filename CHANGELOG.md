# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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

### Fixed

- `deploy/install.sh` health probe now hits the backend over plain HTTP
  (`http://127.0.0.1:8410/api/health`) — previously used `https://`
  which always failed because nginx terminates TLS upstream of the
  backend.
- `deploy/install.sh` pre-flight now exec's the venv's python as the
  `pipeworks` systemd user. Catches the pyenv-private-home trap
  (`status=203/EXEC`) before cert + nginx + systemd are touched and
  prints a rebuild recipe pointing at `/opt/python/3.12.13`.

### Added

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
