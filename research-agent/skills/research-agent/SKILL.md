---
name: research-agent
description: Run or resume an end-to-end, stateful machine-learning research project through evidence-gated literature, gap, idea, experiment, diagnosis, and paper loops. Use when the user wants to explore a research direction, continue a Research Agent project, evaluate a research idea, execute an experimental research loop, or build and review a paper; not for isolated factual questions or one-off brainstorming.
license: Apache-2.0
metadata:
  version: "0.2.0"
---

# Research Agent

This skill runs an end-to-end machine-learning research workflow from broad
topic exploration through evidence-backed experiments, paper drafting, review,
and the final research report. The typed `ResearchState` and its referenced
artifacts are authoritative; chat history is not persistent project state.

## Lifecycle

`BOOTSTRAP → LITERATURE → GAP → TOPIC SELECTION → IDEA → REVIEW → EXPERIMENT →
DIAGNOSIS / ITERATION → EVIDENCE → PAPER → REVIEW → FINAL`

## Invocation protocol

At every invocation:

1. Read and validate the current `ResearchState`; initialize it only for a new
   project.
2. Determine the current research phase and any active human checkpoint.
3. Load `references/scientific_rules.md`, the current phase prompt, and only the
   minimal loop/checkpoint references listed in `manifest.yaml`.
4. Build task-specific context from typed state and referenced artifacts.
5. Execute the current phase using available native reasoning, search, paper,
   repository, coding, shell, experiment, debugging, and writing capabilities.
6. Persist typed state updates, provenance, decisions, evidence, and necessary
   artifacts through the existing runtime.
7. Continue automatically until a checkpoint is reached or required external
   execution is impossible.

Do not load the complete SOP on normal runs. Load only global scientific rules,
current-phase instructions, and relevant project context. Never load
`references/original_sop.md` or `SOP_MAPPING.md` as runtime context; they are
maintenance resources.

## Human checkpoints

- Checkpoint A — Topic Selection
- Checkpoint B — Idea / Resource Input
- Checkpoint C — Major Pivot

Minor implementation, diagnostic, and writing choices are autonomous. A
checkpoint grants no additional execution authority beyond the user's response.

## Detailed guidance

Use `manifest.yaml` for phase routing. Read loop references only when mapped:

- `references/research_loop.md` for literature and GAP phases.
- `references/idea_loop.md` for idea formation and adversarial review.
- `references/experiment_loop.md` for resource, baseline, experiment,
  diagnosis, pivot, and evidence phases.
- `references/paper_loop.md` for readiness, assembly, writing, review, and final
  reporting.
- `references/state_contract.md` only when initializing, recovering, or
  interpreting persistent state.
- `references/checkpoints.md` only when a mapped checkpoint is active.

The skill supplies the research protocol, not replacement implementations for
the host's tools. Prefer verified primary paper sources and use the existing
workflow, state, provenance, execution, and artifact interfaces when available.
