# Contributing

Research Agent favors small, evidence-driven changes over speculative
infrastructure.

## Development setup

```bash
uv sync --extra dev
uv run pytest
uv run python -m compileall -q src
uv build
```

Run the focused Skill checks with:

```bash
uv run pytest tests/test_research_skill.py
```

## Change rules

- Keep `skills/research-agent/` as the single source of truth for the portable
  Skill.
- When adding, removing, or renaming a phase or prompt, update
  `manifest.yaml`, `SOP_MAPPING.md`, and the routing/coverage tests together.
- Do not commit project state, experiment artifacts, downloaded PDFs, logs,
  credentials, local paths, caches, or virtual environments.
- Prefer the host Agent's native search, reading, coding, and shell capabilities
  before adding infrastructure.
- A pull request that adds an abstraction or dependency should state the current
  observed need, the simpler alternatives considered, and how the change is
  tested.
- Keep CI deterministic: no live Codex calls, provider searches, GPU jobs, or
  secrets.

Please describe the behavior changed, evidence for the change, tests run, and
any compatibility or scientific-integrity implications.

