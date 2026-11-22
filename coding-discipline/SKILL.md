---
name: coding-discipline
description: Apply disciplined engineering practices when implementing, debugging, refactoring, or reviewing code changes. Keep changes small and verifiable, avoid redundant Markdown, isolate temporary test artifacts, and keep security limits consistent.
license: MIT
---

# Coding Discipline

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

Adapted from [Karpathy Guidelines](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/skills/karpathy-guidelines/SKILL.md)
by forrestchang and contributors. Apply these defaults within the user's
requested scope, repository rules, and host permissions. Ask when unresolved
uncertainty materially affects the outcome or authorization.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Documentation, Test Artifacts, and Security Limits

### Markdown documentation

- Find the existing authoritative README, guide, or project instruction for
  the topic. Update it when the change affects what its readers need to know.
- Create a Markdown file only when requested or when a durable need such as
  reproducible setup or a maintained interface has no suitable home. Keep
  routine implementation notes and verification results in the handoff.
- Ground commands, settings, and behavior in the implementation, configuration,
  or observed results. Keep each instruction in one authoritative place.

### Temporary test artifacts

- Choose the output location before running checks. Use the test framework's
  temporary directory or a run-specific system temporary directory for
  scratch scripts, generated data, logs, and screenshots.
- Put requested or reproduction-critical outputs in the repository's designated
  artifact location. Track regression tests and fixtures that protect supported
  behavior.
- Remove only disposable artifacts created by this task. Before delivery,
  inspect new and changed paths for stray outputs. Before an authorized
  commit, check the actual staged set for scratch outputs and unrelated changes.

### Security limits and permissions

- Follow the host's effective permissions for actions such as filesystem
  access, network access, and publishing. Keep permission changes within the
  explicit authorization for that change.
- When touching an application limit, identify its authoritative setting, unit,
  effective value in the relevant environment, override precedence, and
  enforcement point. Keep one authoritative definition for each limit and
  apply overrides through the existing configuration path. Derive secondary
  consumers such as input hints from the effective limit. Report unresolved
  conflicts.
- Preserve the existing enforcement and defaults during ordinary changes.
  Keep test overrides scoped to tests. When an authorized change affects a
  limit, verify the effective value and the affected allow or reject behavior.
