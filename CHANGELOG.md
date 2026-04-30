# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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
