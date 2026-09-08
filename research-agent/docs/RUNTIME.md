# Optional Python Runtime

The Python package adds deterministic state and execution boundaries around the
portable Skill. The scientific reasoning remains the responsibility of the
host model; code validates state, tools, transitions, checkpoints, and admitted
results.

```text
LLM performs scientific reasoning.
Code enforces state, tool, transition, and result boundaries.
```

## Components

| Component | Responsibility |
| --- | --- |
| `SkillContextLoader` | Resolve the current phase to a minimal set of Skill resources |
| `ResearchState` | Typed, persistent project state and evidence references |
| `Orchestrator` / workflow engine | Validate actions and phase transitions |
| Literature layer | Search, identity resolution, legal acquisition, parsing, provenance, and quality gates |
| Host Agent | Perform scientific reasoning and use phase-appropriate native tools |
| `ExperimentRunner` | Execute explicitly authorized commands and record outputs |
| Artifact store | Persist source, decision, execution, and paper artifacts outside typed state |

## Progressive disclosure

The runtime composes only:

```text
scientific rules
+ current loop reference
+ current phase prompt
+ active checkpoint prompt, if any
+ bounded project context
```

It does not inject the full archived SOP or the entire project state on every
turn. The canonical source is `skills/research-agent/`; wheel builds map that
same directory into `research_agent/research_skill` inside the installed
package so the CLI can resolve it without a repository checkout.

## Project state

By default, projects live under `./projects/<project-id>/`:

```text
project.yaml
state.json
artifacts/
  literature/
  gaps/
  ideas/
  experiments/
  reviews/
  reports/
  paper/
```

`state.json` stores typed metadata and artifact references; it does not embed
paper PDFs, full logs, or chat transcripts. State writes are atomic. Use
`--projects-root` before the subcommand, or set
`RESEARCH_AGENT_PROJECTS_ROOT`, to move project storage elsewhere.

## Runtime modes

### Mock mode

Mock projects are created with `--mock`. They use deterministic synthetic
fixtures and do not call web providers, a host model, GPUs, or the shell. Mock
fixtures are marked synthetic and cannot be mixed into real projects or become
E2 evidence.

### Live mode

Live mode currently uses the installed `codex` command as its host backend. The
host must be installed and authenticated. Optional overrides are:

- `RESEARCH_AGENT_HOST_COMMAND`
- `RESEARCH_AGENT_HOST_MODEL`
- `CODEX_HOME`

`research-agent doctor PROJECT` reports host, Skill, repository, and execution
readiness without advancing the project. `research-agent run PROJECT --live
--dry-run` inspects the next turn without invoking the host.

## Literature configuration

The built-in providers include arXiv, Crossref, OpenAlex, direct accessible web
pages, and a synthetic mock provider. Provider retrieval never implies content
verification. Optional provider settings include `CROSSREF_MAILTO` and
`OPENALEX_API_KEY`; no credential is required for deterministic tests.

Project-local literature budgets and quality gates live in `project.yaml`.
Full-text acquisition considers only provider-declared open locations and does
not bypass paywalls, authentication, or robots policy.

## Repository and shell boundaries

Attaching a repository records an explicit project dependency; it does not
authorize modification or execution. Shell execution requires both:

1. repository/project configuration `execution.allow_shell: true`; and
2. `ResourceConstraints.shell_execution_allowed: true` from the resource
   checkpoint.

The runner records the command, time, repository identity, tracked diff,
redacted environment overrides, config, stdout, stderr, metrics, duration, and
exit status. Only runner-produced records can become executed experimental
evidence.

## Installation and inspection

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
research-agent --help
```

Useful inspection commands include:

```bash
research-agent status PROJECT
research-agent skill-context PROJECT
research-agent inspect PROJECT state
research-agent literature status PROJECT
```

The complete command list is available from `research-agent --help` and each
subcommand's `--help` output.

