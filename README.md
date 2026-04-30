# PipeWorks Character Forge

Local-only web app that turns one source image into a 25-image character
dataset (PNGs + caption `.txt` files) ready to feed into
[`ostris/ai-toolkit`](https://github.com/ostris/ai-toolkit) for LoRA
training, by chaining image-to-image runs through
`black-forest-labs/FLUX.2-klein-base-9B`.

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
4 action, 9 scenes. Each slot has an editable default prompt; the user
adds a LoRA trigger word that is prepended to every caption at
dataset-export time.

## Layout

- `src/pipeworks_character_forge/` — the FastAPI app + diffusers wrapper.
- `src/pipeworks_character_forge/data/slots.json` — canonical 25-slot
  definition; served to the frontend via `GET /api/slots`.
- `deploy/` — systemd unit, nginx vhost, env example.

Runtime mutable state lives **outside** the repo, mirroring the
`pipeworks-image-generator` convention:

- `/srv/work/pipeworks/runtime/character-forge/models/` — Hugging Face
  cache for the FLUX.2-klein weights.
- `/srv/work/pipeworks/runtime/character-forge/runs/<run_id>/` — outputs
  land here; `dataset/` subdir is the ai-toolkit-ready folder.

## Hostname

Runs at `https://forge.pipeworks.luminal.local` (proxy →
`127.0.0.1:8420`). Single-user, single trust boundary, no auth.

## Deploy on Luminal

`deploy/install.sh` is idempotent and self-checking. Run as a regular
user in the `pipeworks` group; it `sudo`s for the privileged steps:

```bash
bash deploy/install.sh
```

First run drops `/etc/pipeworks/character-forge/character-forge.env`
and exits with a reminder to set `HF_TOKEN`. Edit and re-run:

```bash
sudoedit /etc/pipeworks/character-forge/character-forge.env
bash deploy/install.sh
```

The script:

1. Pre-flight (user, group, mkcert, repo, venv, `[ml]` extras).
2. mkcert leaf cert into `/etc/nginx/certs/`.
3. nginx vhost + reload.
4. Env file install + `HF_TOKEN` validation.
5. systemd link + `enable --now`.
6. Health probe against `https://127.0.0.1:8420/api/health`.

Manual follow-ups (script reminds at the end):

- DrayTek LAN DNS: `forge.pipeworks.luminal.local` → `192.168.20.11`
- `/etc/luminal/services.yml` registration

Clean rollback: `bash deploy/uninstall.sh` (leaves the venv, repo, and
runtime cache intact — remove those by hand if needed).

## Status

PR 1 — repo skeleton + deploy plumbing, no model loading yet. See
`CHANGELOG.md` for what is currently on `main`.
