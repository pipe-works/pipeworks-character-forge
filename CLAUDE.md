# Claude notes

See `AGENTS.md` for the load-bearing constraints. A few extra hints
specific to AI-assisted iteration on this repo:

- The venv lives at `/srv/work/pipeworks/venvs/pw-character-forge`. Use
  it directly via absolute path; do not assume PATH has it.
- Format with `black src tests` and lint with `ruff check src tests`.
  Both are pinned in `[project.optional-dependencies].dev`.
- Tests run with `pytest` (configured in `pyproject.toml`). The
  `pipeline_orchestrator` module is designed so its tests can run
  without a GPU by injecting a fake `Flux2KleinManager`.
- Before opening a PR: `black`, `ruff check`, `mypy src`, `pytest` —
  all clean.
- Branch-per-change PR workflow: never commit directly to `main`.
