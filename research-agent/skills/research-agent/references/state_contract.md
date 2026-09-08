# Research State Contract

Use the existing versioned `ResearchState`; never create a parallel state system.
Load and validate it before acting, then persist it atomically after a valid
transition. It supplies the project direction, current phase, selected GAP,
active hypotheses, selected method, resource constraints, verified literature,
experiment and decision ledgers, evidence, claims, paper status, next actions,
and any active checkpoint.

State stores typed metadata and artifact paths. Large paper contents, logs,
metrics, reviews, packages, drafts, and reports belong in the artifact store.
Chat history, filenames, model prose, and synthetic fixtures are not evidence.

The LLM or host agent proposes scientific decisions; deterministic code validates
actions, transitions, schemas, checkpoints, execution records, and evidence
promotion. Reuse the current typed action/state-update structures. Runtime must
be able to recover at least:

```yaml
state_update: {}
new_evidence: []
active_hypotheses: []
rejected_hypotheses: []
decisions: []
uncertainties: []
next_action: null
need_human_input: false
```

Build bounded context for the current task. Do not inject all papers, logs,
reviews, or the archived SOP. Never infer shell, GPU, API, data, license, or
external-write authority from state unless the relevant explicit authorization
is present.

