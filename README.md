[![CI](https://github.com/pipe-works/pipeworks-character-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe-works/pipeworks-character-forge/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pipe-works/pipeworks-character-forge/branch/main/graph/badge.svg)](https://codecov.io/gh/pipe-works/pipeworks-character-forge)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# pipeworks-character-forge

`pipeworks-character-forge` is the PipeWorks character dataset forge. It turns
one source image into a 25-image character dataset (PNGs plus matching caption
`.txt` files) ready to feed into [`ostris/ai-toolkit`](https://github.com/ostris/ai-toolkit)
for LoRA training, by chaining image-to-image runs through
`black-forest-labs/FLUX.2-klein-base-9B`. It combines a FastAPI API, a vanilla
HTML/CSS/JS frontend, a single-worker GPU job queue, and disk-backed run
manifests for iterative dataset curation.

## PipeWorks Workspace

These repositories are designed to live inside a shared PipeWorks workspace
rooted at `/srv/work/pipeworks`.

- `repos/` contains source checkouts only.
- `venvs/` contains per-project virtual environments such as `pw-mud-server`.
- `runtime/` contains mutable runtime state such as databases, exports, session
  files, and caches.
- `logs/` contains service-owned log output when a project writes logs outside
  the process manager.
- `config/` contains workspace-level configuration files that should not be
  treated as source.
- `bin/` contains optional workspace helper scripts.
- `home/` is reserved for workspace-local user data when a project needs it.

Across the PipeWorks ecosphere, the rule is simple: keep source in `repos/`,
keep mutable state outside the repo checkout, and use explicit paths between
repos when one project depends on another.

## What This Repo Owns

This repository is the source of truth for:

- the `pw-forge` CLI entry point (`serve` and `make-dataset` subcommands)
- the FastAPI application under `src/pipeworks_character_forge/api/`
- the canonical 25-slot definition at
  `src/pipeworks_character_forge/data/slots.json`
- the FLUX.2-klein image-to-image manager and pipeline orchestrator
- disk-backed run manifests, the single-worker GPU job queue, and the
  cascade / cancel / dataset-export semantics layered on top
- the browser UI and static assets under
  `src/pipeworks_character_forge/templates/` and
  `src/pipeworks_character_forge/static/`
- deployment templates under `deploy/`

This repository does not own:

- the FLUX.2-klein-base-9B weights themselves (pulled from Hugging Face)
- the downstream LoRA trainer (`ostris/ai-toolkit` is a consumer of the
  exported dataset directory, not part of this repo)
- broader workspace-level host operations outside this repo's own deploy
  templates

## Pipeline

```text
source.png
    │
    ▼  prompt: "Create an image of this exact character in this style."
00_stylized_base.png   ◄─────────── reference for every leaf below
    │
    ├─► 01_turnaround.png    (full body, four poses, white background)
    ├─► 02_t_pose.png
    ├─► 03_side_3q.png
    ├─► 04_back_3q.png
    ├─► 05_extreme_closeup.png
    ├─► …
    └─► 25_golden_hour_rooftop.png
```

The 25 leaves are grouped: 4 reference, 3 portrait framing, 5 expressions,
4 action, 9 scenes. Each slot has an editable default prompt; the operator
sets a LoRA trigger word that is prepended to every caption at
dataset-export time. An optional `style_prefix` is prepended to every prompt
at generation time to lock visual identity across all 26 outputs (it is not
baked into captions).

Every i2i call uses a deterministic seed of
`run_seed + slot_order + 1000 * regen_count`, so reruns are reproducible
and per-tile regenerates never collide.

## Main App Surfaces

### Browser UI

The browser UI provides:

- source image upload and trigger-word entry
- optional global style prefix and per-slot prompt overrides
- the 26-tile gallery (promoted stylized base plus 25 leaves) with per-tile
  prompt editing, regenerate, and "Include in dataset" toggling
- selective initial generation, batch regenerate, and stylized-base cascade
- a one-click **Create dataset** button equivalent to the CLI export
- light/dark theme toggle persisted to `localStorage`

### FastAPI API

The API exposes:

- `GET /api/health` and `GET /api/slots`
- `POST /api/source` for source-image upload
- `POST /api/runs` and `GET /api/runs[/{run_id}]` for run creation and polling
- `POST /api/runs/{run_id}/slots/{slot_id}/regenerate` for per-slot regenerate
- `POST /api/runs/{run_id}/cascade` for stylized-base cascade re-runs
- `POST /api/runs/{run_id}/cancel` for best-effort mid-run cancellation
- `PATCH /api/runs/{run_id}/slots/{slot_id}` for `excluded` and `prompt`
  overrides
- `POST /api/runs/{run_id}/dataset` for one-click dataset export
- `GET /api/debug/*` for development utilities
- `/static/...` and `/runs/<run_id>/<filename>` static mounts for the UI and
  generated images

### Execution Model

Generation is single-GPU and serialized: a single-worker FIFO `JobQueue`
wraps the orchestrator so the GPU is never multiplexed. FLUX.2-klein-base-9B
in bf16 weighs roughly 30 GiB resident, so `enable_model_cpu_offload` is on
by default; on a 32 GiB card peak measured at ~18.5 GiB and ~52 s per i2i
call. Disable offload only on cards with substantially more VRAM
(A100 80 GB, H100, etc.).

## Relationship To Other PipeWorks Repos

- `pipeworks-image-generator` — sibling browser-facing image-generation app
  whose `pipe-works-base.css` design tokens and theme convention this repo
  consumes verbatim
- `pipeworks-policy-workbench` — operator workbench for policy objects;
  unrelated to dataset forging but shares the same workspace conventions
- `ostris/ai-toolkit` — external LoRA trainer that consumes the
  `dataset/` directory produced by `pw-forge make-dataset`

The forge does not own policy or training; it produces a clean training
dataset directory and stops.

## Repository Layout

- `src/pipeworks_character_forge/api/main.py` FastAPI bootstrap, lifespan,
  router registration, and the `pw-forge serve` entry point
- `src/pipeworks_character_forge/api/routers/` route groups for runs,
  slots, source upload, and debug endpoints
- `src/pipeworks_character_forge/api/services/` `slot_catalog`,
  `run_store`, `job_queue`, and `pipeline_orchestrator`
- `src/pipeworks_character_forge/core/config.py` Pydantic settings with the
  `PIPEWORKS_FORGE_` env prefix
- `src/pipeworks_character_forge/core/flux2_manager.py` diffusers pipeline
  lifecycle and image-to-image generation
- `src/pipeworks_character_forge/core/image_io.py` PNG / caption I/O helpers
- `src/pipeworks_character_forge/cli/` argparse dispatch and the
  `make-dataset` exporter
- `src/pipeworks_character_forge/data/slots.json` canonical 25-slot
  definition
- `src/pipeworks_character_forge/templates/index.html` browser UI shell
- `src/pipeworks_character_forge/static/` CSS, fonts, and ES-module frontend
- `tests/` unit and API coverage
- `deploy/` example env, `systemd`, `nginx`, and `install.sh` / `uninstall.sh`

## Quick Start

### Requirements

- Python `>=3.12,<3.13` (pinned for PyTorch / diffusers compatibility on
  the FLUX.2-klein stack)
- a PipeWorks workspace rooted at `/srv/work/pipeworks`
- a CUDA-capable GPU and the `[ml]` extra installed for inference
- a Hugging Face access token with read scope, for the initial pull of
  `black-forest-labs/FLUX.2-klein-base-9B`
- sufficient disk space for the model cache and per-run output directories

### Install

Create a project venv and install from `pyproject.toml`. The base install
omits torch/diffusers; the `[ml]` extra adds them for inference:

```bash
python3.12 -m venv /srv/work/pipeworks/venvs/pw-character-forge
/srv/work/pipeworks/venvs/pw-character-forge/bin/pip install -e ".[dev,ml]"
```

For host-managed service use, the venv should be built from a system-level
Python `3.12` install rather than from a user-home interpreter; see
`AGENTS.md` for the rationale.

### Prepare Runtime Paths

Mutable state lives outside the repo checkout. The defaults already point
at the workspace:

- model cache under `/srv/work/pipeworks/runtime/character-forge/models/`
- per-run outputs under `/srv/work/pipeworks/runtime/character-forge/runs/<run_id>/`
  (with a `dataset/` subdirectory once exported)
- workspace-managed env/config under
  `/srv/work/pipeworks/config/character-forge/` when running outside the
  repo checkout

### Prepare Environment

For local development:

```bash
cp deploy/env/character-forge.env.example .env
```

All variables use the `PIPEWORKS_FORGE_` prefix. Important variables in
the current codebase include:

- `PIPEWORKS_FORGE_SERVER_HOST` (default `127.0.0.1`)
- `PIPEWORKS_FORGE_SERVER_PORT` (default `8420`)
- `PIPEWORKS_FORGE_RUNS_DIR`
- `PIPEWORKS_FORGE_MODELS_DIR`
- `PIPEWORKS_FORGE_FLUX2_MODEL_ID`
- `PIPEWORKS_FORGE_DEVICE`
- `PIPEWORKS_FORGE_TORCH_DTYPE`
- `PIPEWORKS_FORGE_DEFAULT_STEPS`
- `PIPEWORKS_FORGE_DEFAULT_GUIDANCE`
- `PIPEWORKS_FORGE_ENABLE_ATTENTION_SLICING`
- `PIPEWORKS_FORGE_ENABLE_MODEL_CPU_OFFLOAD`
- `PIPEWORKS_FORGE_LOG_LEVEL`

Hugging Face token setup:

```bash
export HF_TOKEN=your_token_here
```

Or place it in your local `.env`. The token is required on a fresh
machine to pull the gated FLUX.2-klein-base-9B weights; once cached
under `MODELS_DIR` it is no longer required at runtime.

### Run Locally

```bash
/srv/work/pipeworks/venvs/pw-character-forge/bin/pw-forge
```

`pw-forge` with no subcommand is equivalent to `pw-forge serve` and runs
the FastAPI server. The repo-local default bind is `127.0.0.1:8420`;
hosted deployments terminate TLS in nginx upstream of this loopback bind.

### Export A Dataset

Once a run reaches `status: done`, write a clean training folder for
ai-toolkit either through the UI's **Create dataset** button or the CLI:

```bash
/srv/work/pipeworks/venvs/pw-character-forge/bin/pw-forge \
    make-dataset <run_id>
```

That writes `<run-dir>/dataset/` containing only the leaf
`NN_<slot>.png` + `NN_<slot>.txt` pairs (no source image, no manifest, no
intermediate stylized base, and no slots flagged `excluded`). Point your
ai-toolkit config's `dataset_path` at it and train.

Flags: `--output-dir / -o <path>` to write somewhere else,
`--force / -f` to overwrite an existing dataset folder. The command exits
non-zero if the run is unknown, incomplete, or the target exists without
`--force`, and warns on stderr when `trigger_word` is empty.

## Runtime Conventions

- The 25-slot catalog at
  `src/pipeworks_character_forge/data/slots.json` is canonical; the
  frontend fetches it via `GET /api/slots` and never duplicates the slot
  list in JS.
- Run manifests are disk-backed under `<runs_dir>/<run_id>/manifest.json`
  with atomic tmp + `os.replace` writes; the orchestrator re-reads
  `cancel_requested` from disk before every save so an external HTTP
  cancel cannot be clobbered mid-chain.
- Generated images are served at `/runs/<run_id>/NN_<slot>.png` via a
  static mount; the lifespan hook creates `runs_dir` on startup so the
  mount uses `check_dir=False`.
- The browser UI imports the shared `pipe-works-base.css` design tokens
  and Crimson Text / Courier Prime font set used across the PipeWorks
  ecosphere; `forge.css` only contains layout-specific rules.

## Validation And Development

Run the main checks from the repo root:

```bash
/srv/work/pipeworks/venvs/pw-character-forge/bin/pytest -q
/srv/work/pipeworks/venvs/pw-character-forge/bin/ruff check src tests
/srv/work/pipeworks/venvs/pw-character-forge/bin/black --check src tests
/srv/work/pipeworks/venvs/pw-character-forge/bin/mypy src
```

Useful targeted checks:

```bash
/srv/work/pipeworks/venvs/pw-character-forge/bin/pytest tests/test_api_runs.py -q
/srv/work/pipeworks/venvs/pw-character-forge/bin/pytest tests/test_pipeline_orchestrator.py -q
```

The test suite stubs out the FLUX.2-klein manager via `tests/_fakes.py`,
so unit and API tests run without a GPU.

## Deployment Templates

Host-neutral deployment examples are shipped in:

- `deploy/env/character-forge.env.example`
- `deploy/systemd/pipeworks-character-forge.service`
- `deploy/nginx/forge.pipeworks.luminal.local`
- `deploy/install.sh` and `deploy/uninstall.sh` (idempotent, self-checking)

These are deployment templates, not the runtime authority themselves. Keep
machine-specific rollout detail in runbooks, MOCs, or host-level docs
rather than in this README.

## Documentation

Additional documentation lives in:

- `CHANGELOG.md`
- `AGENTS.md`
- `CLAUDE.md`

## License

[GPL-3.0-or-later](LICENSE)
