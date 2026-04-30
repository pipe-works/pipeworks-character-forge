# Agent notes — pipeworks-character-forge

This repo is intended for assisted development. A few load-bearing
constraints worth knowing before editing.

## Python pin

`requires-python = ">=3.12,<3.13"`. Hard-pinned to 3.12 for PyTorch /
diffusers compatibility on the FLUX.2-klein stack. Do not relax this
without verifying the diffusers + torch wheels for the next minor.

### Canonical interpreter for venvs on Luminal

Use `/opt/python/3.12.13/bin/python3.12` when creating the venv at
`/srv/work/pipeworks/venvs/pw-character-forge`. Do **not** use a
pyenv-managed python under `~/.pyenv/` — the systemd unit runs as
`pipeworks`, your home dir is mode `0700`, and the resulting symlink
chain causes `status=203/EXEC` (permission denied) at unit start.
`deploy/install.sh` pre-flights this with `sudo -u pipeworks
$VENV/bin/python --version` and bails out with a rebuild recipe.

Convention: chown the venv `pipeworks:pipeworks` with mode 0775 +
setgid so any member of the `pipeworks` group can `pip install` into
it later.

## Top-level package name

`pipeworks_character_forge`. Distinct from the bare `pipeworks` namespace
used by the older `pipeworks-image-generator` repo, deliberately, so two
venvs activated in the same shell do not collide.

## Slot catalog is canonical

`src/pipeworks_character_forge/data/slots.json` is the single source of
truth for the 25 slots. The frontend fetches it via `GET /api/slots`.
Do not duplicate the slot list in JS.

## Hostname

`forge.pipeworks.luminal.local` is the canonical hostname. Sub-zone of
`pipeworks.luminal.local`, mirroring `images.pipeworks.luminal.local`
for `pipeworks-image-generator`. Never bind to `0.0.0.0` in dev — local
only.

## Deploy is operator action

Files under `deploy/` are committed to the repo. Installing them
(`systemctl link`, nginx vhost copy, mkcert cert issuance, DNS LAN
entry) is a separate operator step, not part of any code PR's runtime
change.
