# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
