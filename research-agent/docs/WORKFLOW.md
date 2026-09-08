# Research Workflow

Research Agent is a stateful decision loop, not a fixed sequence that always
ends in a paper. Each phase should produce evidence or a decision that changes
what happens next.

## Research loop

The outer loop is:

```text
direction -> literature -> candidate gaps -> selected gap
          -> hypotheses -> experiments -> evidence -> paper audit
```

Literature retrieval and verification are separate. A paper candidate is not a
verified source, and metadata verification does not support detailed claims
about methods, limitations, ablations, or results. Gap synthesis requires
traceable source statements and preserves contradictory evidence.

Checkpoint A pauses after 3–5 candidate GAPs have been synthesized. The
researcher selects the primary problem; the Agent does not silently optimize a
topic choice on the researcher's behalf.

## Idea loop

The selected GAP becomes a small tree of competing, falsifiable hypotheses.
The workflow then performs:

```text
formation -> adversarial attack -> revision or defense -> meta-review
```

The review asks whether the problem is real and observable, whether equivalent
work already exists, whether a simpler baseline explains the expected gain,
and which result would falsify the motivation. A method is not accepted merely
because its modules form a coherent architecture.

Checkpoint B records the researcher's idea input and actual resource
constraints. The minimum experiment should answer the highest-value scientific
question within those constraints.

## Experiment loop

Experiments progress from low-cost diagnostics to stronger evidence:

1. Establish that the claimed phenomenon exists and is not an evaluation or
   implementation artifact.
2. Reproduce the strongest relevant baseline under a matched protocol.
3. Test the minimum intervention against strong simple controls.
4. Diagnose negative or ambiguous outcomes before changing the method.
5. Expand evidence only after a decision-relevant signal survives checks.

A negative result is not discarded. It enters diagnosis with the observation
separated from interpretation:

```text
Observation != Interpretation
```

Candidate causes are hypotheses until a discriminative test identifies a root
cause. The workflow may continue, modify, stop, or propose a pivot. Checkpoint C
is used only for a major change to the research direction; ordinary debugging
and local revisions do not require it.

## Paper loop

The paper loop begins with an evidence audit, not prose generation:

```text
claim-evidence matrix -> missing-evidence decision -> package -> draft -> review
```

If a central claim lacks adequate support, the workflow returns to experiments
or narrows the claim. Review may also send the project back to diagnosis or
evidence expansion. Incremental research is valid when the problem, comparison,
and evidence are clear; novelty language must stay bounded by the searched
literature.

## Evidence levels

The runtime distinguishes:

- **E0:** hypothesis or speculation
- **E1:** verified, non-synthetic literature evidence
- **E2:** one completed, runner-verified non-synthetic experiment
- **E3:** replicated executed seeds
- **E4:** robust evidence across relevant settings

Synthetic mock fixtures cannot be promoted into scientific evidence. A host
Agent's textual claim cannot replace a runner record, source artifact, or
verified citation.

## Phase resources

The canonical routing map is
[`manifest.yaml`](../skills/research-agent/manifest.yaml). Every invocation
loads global scientific rules plus the current loop and phase prompt. The
archived original SOP is a maintenance source and is never the normal runtime
context.

