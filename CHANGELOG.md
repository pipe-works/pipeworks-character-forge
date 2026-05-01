# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0](https://github.com/pipe-works/pipeworks-character-forge/compare/pipeworks-character-forge-v0.1.0...pipeworks-character-forge-v0.2.0) (2026-05-01)


### Features

* 25-slot pipeline orchestrator + run/regenerate API ([#9](https://github.com/pipe-works/pipeworks-character-forge/issues/9)) ([4a0f6e1](https://github.com/pipe-works/pipeworks-character-forge/commit/4a0f6e14505900a871473b7dc8586da40226bba4))
* add idempotent deploy/install.sh + uninstall.sh for Luminal ([#7](https://github.com/pipe-works/pipeworks-character-forge/issues/7)) ([14c30bc](https://github.com/pipe-works/pipeworks-character-forge/commit/14c30bc879f4cc4d466cd0318877b96f680872c8))
* batch regenerate via tile checkboxes + stylized-base cascade ([#19](https://github.com/pipe-works/pipeworks-character-forge/issues/19)) ([98029e4](https://github.com/pipe-works/pipeworks-character-forge/commit/98029e4626a20315a88e5631d7268a41db5b81c6))
* bootstrap PipeWorks Character Forge skeleton ([#1](https://github.com/pipe-works/pipeworks-character-forge/issues/1)) ([1718caf](https://github.com/pipe-works/pipeworks-character-forge/commit/1718caff2ce601ae76a99d3fd7e3a801d3aa062d))
* cancel a running chain (best-effort) + reset gallery on cancel ([#17](https://github.com/pipe-works/pipeworks-character-forge/issues/17)) ([82ccb7d](https://github.com/pipe-works/pipeworks-character-forge/commit/82ccb7dce818e0d4187f6b9151c849ae1aa16451))
* FLUX.2-klein manager + source upload + debug i2i endpoint ([#4](https://github.com/pipe-works/pipeworks-character-forge/issues/4)) ([2dad7a3](https://github.com/pipe-works/pipeworks-character-forge/commit/2dad7a3c9ded430991ddfc4185fe4fc60e9efeaa))
* frontend (HTML + ES modules + CSS) ([#10](https://github.com/pipe-works/pipeworks-character-forge/issues/10)) ([ea57b30](https://github.com/pipe-works/pipeworks-character-forge/commit/ea57b3039b84c1af378709aff741292a4ab03052))
* per-slot exclude-from-dataset toggle ([#18](https://github.com/pipe-works/pipeworks-character-forge/issues/18)) ([21a1107](https://github.com/pipe-works/pipeworks-character-forge/commit/21a11073af93468de39964a453db77cd80b07356))
* pw-forge make-dataset CLI + UMask=0002 on systemd unit ([#11](https://github.com/pipe-works/pipeworks-character-forge/issues/11)) ([a9061f3](https://github.com/pipe-works/pipeworks-character-forge/commit/a9061f3c9a88f8ae976a77fa227f3898c889cd09))
* selective initial generation — generate just selected slots ([#21](https://github.com/pipe-works/pipeworks-character-forge/issues/21)) ([3e02ebc](https://github.com/pipe-works/pipeworks-character-forge/commit/3e02ebc17508df662e695a69f90ef427361e8ba9))
* style-prefix run param + Create-dataset HTTP endpoint and button ([#16](https://github.com/pipe-works/pipeworks-character-forge/issues/16)) ([44e7b6a](https://github.com/pipe-works/pipeworks-character-forge/commit/44e7b6a8ddebf389833046eed932f3c1cdca0a06))
* **theme:** app-shell layout + light/dark toggle, design tokens ([#12](https://github.com/pipe-works/pipeworks-character-forge/issues/12)) ([5c450cf](https://github.com/pipe-works/pipeworks-character-forge/commit/5c450cfd854dcff9b973abf0de38b986e54cc248))


### Fixes

* **css:** [hidden] !important so tiles do not render as broken-image alt text ([#13](https://github.com/pipe-works/pipeworks-character-forge/issues/13)) ([342b7a1](https://github.com/pipe-works/pipeworks-character-forge/commit/342b7a19cc4a5a646ad5e5569ff2b61c84d76d1a))
* **css:** stack seed/steps/guidance fields vertically in the source panel ([#15](https://github.com/pipe-works/pipeworks-character-forge/issues/15)) ([48e109d](https://github.com/pipe-works/pipeworks-character-forge/commit/48e109d851cba7ae98b6b93d5d20e070b9a890ec))
* default enable_model_cpu_offload=true for 32 GiB cards ([#6](https://github.com/pipe-works/pipeworks-character-forge/issues/6)) ([cd374fa](https://github.com/pipe-works/pipeworks-character-forge/commit/cd374fab54c1b3233960479262586293a5806ef9))
* **install:** correct health-probe URL + pre-flight venv exec by pipeworks ([#8](https://github.com/pipe-works/pipeworks-character-forge/issues/8)) ([e0c7f44](https://github.com/pipe-works/pipeworks-character-forge/commit/e0c7f443366d685af82df9bce2eed32e87f2f20a))
* **ui:** drop tile shimmer + remove redundant click that double-opens file dialog ([#14](https://github.com/pipe-works/pipeworks-character-forge/issues/14)) ([4582260](https://github.com/pipe-works/pipeworks-character-forge/commit/45822607e0a79877e1eaece5848b093b6d6eecf0))
* **ui:** tile select checkboxes only operable when a run exists ([#20](https://github.com/pipe-works/pipeworks-character-forge/issues/20)) ([f4df9c8](https://github.com/pipe-works/pipeworks-character-forge/commit/f4df9c83bd171a569f9424e953328288722c5a6f))


### Documentation

* **readme:** rewrite to comply with PipeWorks README policy ([#22](https://github.com/pipe-works/pipeworks-character-forge/issues/22)) ([d6018d3](https://github.com/pipe-works/pipeworks-character-forge/commit/d6018d3c545e0f6e2659ae6b070a0ad9dbaa1352))


### Internal Changes

* move runtime state outside the repo + document HF_TOKEN ([#5](https://github.com/pipe-works/pipeworks-character-forge/issues/5)) ([3bdcbdd](https://github.com/pipe-works/pipeworks-character-forge/commit/3bdcbdde6f3201e14900504cc905804a6e110e0d))

## [Unreleased]

### Added

- **Selective initial generation** — tile select checkboxes are now
  always operable (reverting the disable from the prior fix). With a
  selection on a fresh page, the *Generate all 25* button flips to
  *Generate selected (N)* and creates a run that produces only the
  stylized base + the selected leaves. Other slots stay `pending` so
  the operator can fill them in later via per-tile regenerate.
  Iteration cost on one prompt drops from ~25 minutes to ~2 minutes
  (base + 1 leaf at ~52 s each on the 5090 with cpu_offload).
  - New `RunManifest.only_slots: list[str] | None` (None = full chain).
  - `POST /api/runs` accepts `only_slots`. Stylized base ids are
    silently stripped from the list (the base always runs because every
    leaf uses it as conditioning input).
  - Unknown slot ids in `only_slots` return 400.
- **Batch regenerate** — per-tile select checkbox in the tile header.
  Ticking ≥1 tile flips the *Generate all 25* button to *Regenerate
  selected (N)*; clicking it queues N regenerates through the existing
  `POST /api/runs/{id}/slots/{slot}/regenerate` endpoint, dispatched
  one at a time by the GPU's FIFO worker. The selection clears once
  queued so the next iteration starts clean.
- **Stylized base cascade** — selecting *only* `stylized_base` shows
  a confirm dialog ("Cascade — re-run base AND all 25 leaves" vs
  "Just the base"). Cascade hits a new `POST /api/runs/{id}/cascade`
  endpoint that re-runs the base + every leaf in display order while
  preserving operator prompt edits and `excluded` flags. Without
  cascade the base regenerates alone, leaving existing leaves
  referencing the old base on disk (operator's choice — useful for
  iterating on the base look without losing curated leaves).
- New orchestrator method `cascade_from_base(run_id)` and matching
  `JobQueue.enqueue_cascade(run_id)`. The cascade bumps `regen_count`
  on every slot deterministically so seeds shift and the leaves
  follow the new latent space rather than colliding with the previous
  run's seeds.
- **Exclude from dataset** — per-slot toggle to curate drifted leaves
  out of the LoRA training set without deleting them from disk.
  - `SlotState` gains `excluded: bool = False`.
  - New `PATCH /api/runs/{run_id}/slots/{slot_id}` endpoint with
    `{excluded, prompt}` body — both fields optional, change only what
    you pass. Backed the existing `prompt` override too, since it was
    a natural fit for the same metadata-only patch route.
  - `pw-forge make-dataset` and `POST /api/runs/{id}/dataset` skip
    excluded slots; the result counts them in a separate `excluded`
    list (informational, not an error). CLI prints them on stderr.
  - Frontend tile gets a small "Include" checkbox. Default checked;
    unchecking it dims the tile (50% opacity, slight grayscale) and
    immediately PATCHes the manifest. The stylized base tile hides
    the checkbox — the intermediate is always excluded by definition.
- **Cancel run** — best-effort mid-run cancellation. New
  `POST /api/runs/{run_id}/cancel` endpoint flips a flag the
  orchestrator polls between slots; the in-flight i2i call (~52 s)
  cannot be interrupted and finishes naturally, but no further slots
  start. Run status transitions to `cancelled`; slots that already
  produced PNGs keep their files on disk for inspection. Frontend
  exposes a Cancel button that's only visible while the run is
  `running`; on cancel, the gallery resets to the blank/pending
  state and the partial outputs remain available under
  `runs/<run_id>/`.
- Race-safe manifest saves: the orchestrator now reads `cancel_requested`
  from disk before every save so an external HTTP cancel cannot be
  clobbered by a subsequent slot save mid-chain.
- **Style prefix** — optional global text prepended to every slot's
  prompt at generation time. Locks visual identity across all 26
  outputs against scene prompts that describe photographic lighting
  setups (which otherwise pull FLUX.2-klein away from the source's
  art style — observed on the spooky-castle / rainy-street scenes
  during the linocut character run). Stored on the manifest so per-
  tile regenerates pick it up. **Not** baked into captions: the
  LoRA learns style from the images themselves; baking the prefix
  into captions would force the trigger word to be used together
  with the prefix at inference time.
  - New `style_prefix` field on `RunManifest`.
  - `POST /api/runs` accepts `style_prefix` in the body.
  - `PipelineOrchestrator._compose_prompt` does the prepending.
  - Frontend gets a "Style prefix" textarea in the source panel
    with the linocut/sepia placeholder as a worked example.
- **Create dataset button** — one-click HTTP equivalent of
  `pw-forge make-dataset`:
  - New `POST /api/runs/{run_id}/dataset` endpoint, backed by the
    same `export_run_dataset` core function the CLI uses (extracted
    from `cli/make_dataset.py` so behavior is identical between
    SSH and one-click flows).
  - Always overwrites any existing `dataset/` subdir.
  - Frontend "Create dataset" button enabled once the run reaches
    `done`; click → POST → status bar shows the path + pair count;
    button briefly flips to "Dataset created ✓".
  - Errors map to HTTP statuses: 404 unknown run, 409 incomplete or
    output dir collision (with `force=False`).
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
