# Research Agent LOOP v1 — SOP Mapping

This maintenance map records where each part of the archived SOP is enforced.
Runtime uses `manifest.yaml`; it does not load this file.

## Phase and scientific behavior coverage

| Original SOP section | Skill file | Runtime phase |
|---|---|---|
| Global scientific integrity and evidence-first rules | `references/scientific_rules.md` | All phases |
| P0 Research Bootstrap | `prompts/bootstrap.md` | `BOOTSTRAP` |
| P1 Horizon Scan and Literature Landscape | `references/research_loop.md`, `prompts/horizon_scan.md` | `HORIZON_SCAN` |
| Literature verification, provenance, extraction quality and versions | `references/research_loop.md` | Literature and GAP phases |
| P2 GAP Mining | `prompts/gap_mining.md` | `GAP_MINING` |
| P3 GAP Synthesis | `prompts/gap_synthesis.md` | `GAP_SYNTHESIS` |
| Topic Selection | `references/checkpoints.md`, `prompts/checkpoint_topic.md` | `TOPIC_SELECTION` checkpoint |
| Idea Formation | `references/idea_loop.md`, `prompts/idea_formation.md` | `IDEA_FORMATION` |
| Idea Attack | `prompts/idea_attack.md` | `IDEA_REVIEW` |
| Idea Defense | `prompts/idea_defense.md` | `IDEA_REVIEW` |
| Meta Review | `prompts/meta_review.md` | `IDEA_REVIEW` |
| Idea / Resource Input | `references/checkpoints.md`, `prompts/checkpoint_resources.md` | `RESOURCE_DESIGN` checkpoint |
| Resource-aware Experiment Designer | `references/experiment_loop.md`, `prompts/experiment_design.md` | `RESOURCE_DESIGN` |
| Baseline Reproduction Gate | `prompts/baseline_reproduction.md` | `BASELINE_REPRODUCTION` |
| Core Experiment Loop and result analysis | `references/experiment_loop.md`, `prompts/core_experiment.md` | `CORE_EXPERIMENT` |
| Experiment Diagnosis | `prompts/diagnosis.md` | `DIAGNOSIS` |
| Stopping and Pivot Policy | `references/experiment_loop.md`, `prompts/pivot.md` | `PIVOT` |
| Major Pivot checkpoint | `references/checkpoints.md`, `prompts/checkpoint_pivot.md` | `PIVOT` checkpoint |
| Evidence Expansion | `prompts/evidence_expansion.md` | `EVIDENCE_EXPANSION` |
| Paper Readiness Auditor | `references/paper_loop.md`, `prompts/paper_readiness.md` | `PAPER_AUDIT` |
| Paper Package | `prompts/paper_package.md` | `PAPER_ASSEMBLY` |
| Paper Writer | `prompts/paper_writer.md` | `PAPER_ASSEMBLY` / `PAPER_WRITING` alias |
| Paper Review and return-to-experiment loop | `references/paper_loop.md`, `prompts/paper_review.md` | `PAPER_REVIEW` |
| Final Research Report | `prompts/research_report.md` | `COMPLETE` / `FINAL_REPORT` alias |
| Typed state, action, artifact, context and authority contract | `references/state_contract.md` | Bootstrap, recovery, and runtime implementation |

## Foundational specification coverage

| Archived specification section | Skill destination | Runtime relevance |
|---|---|---|
| 1. Prompt role is not agent process | `references/state_contract.md` | All runtime composition |
| 2. LLM decides; code validates transitions | `references/state_contract.md` | All transitions |
| 3–5. Typed persistent state and core schemas | `references/state_contract.md` | State load/update |
| 6. Evidence levels and Claim contract | `references/scientific_rules.md`, `references/paper_loop.md` | Experiment, evidence, paper |
| 7–8. Structured actions and orchestrator | `references/state_contract.md` | Orchestration |
| 9–10. Bounded context and file-backed prompts | `SKILL.md`, `manifest.yaml`, `references/state_contract.md` | Every invocation |
| 11–12. Provider-neutral LLM/tool use | `SKILL.md`, `references/state_contract.md` | Tool use |
| 13. Literature workflow | `references/research_loop.md`, research prompts | Horizon through GAP synthesis |
| 14. Human checkpoints | `references/checkpoints.md`, checkpoint prompts | Three checkpoint types |
| 15. Idea review loop | `references/idea_loop.md`, review prompts | Idea review |
| 16. L0–L5 experiment workflow | `references/experiment_loop.md`, `prompts/experiment_design.md` | Experiment design |
| 17. Baseline gate | `prompts/baseline_reproduction.md` | Baseline reproduction |
| 18. Runner-backed evidence | `references/experiment_loop.md`, `prompts/core_experiment.md` | Execution |
| 19. Diagnosis loop | `references/experiment_loop.md`, `prompts/diagnosis.md` | Diagnosis |
| 20. Stop/pivot policy | `references/experiment_loop.md`, `prompts/pivot.md` | Diagnosis and pivot |
| 21. Paper workflow | `references/paper_loop.md`, paper prompts | Paper phases |
| 22. Research Skill | `SKILL.md`, `manifest.yaml` | Skill entry and routing |
| 23–25. CLI, lifecycle, and mock isolation | `references/state_contract.md` | Runtime implementation |
| 26–30. Tests, logging, configuration, docs, engineering boundaries | `references/state_contract.md`; repository implementation/tests | Maintenance, not phase context |
| 31. Historical implementation milestones | `references/original_sop.md` | Archive only |
| 32. Evidence-led working method | `references/scientific_rules.md`, `references/state_contract.md` | All phases |
| 33. Original acceptance criteria | `manifest.yaml`, repository tests | Maintenance |

## Completeness rule

Every behavior-level entry in `manifest.yaml:sop_coverage` must resolve to an
existing file. Adding, removing, or renaming a phase/checkpoint requires updating
the manifest, this map, and the coverage/progressive-loading tests in the same
change. The archived `references/original_sop.md` is never a runtime fallback.

