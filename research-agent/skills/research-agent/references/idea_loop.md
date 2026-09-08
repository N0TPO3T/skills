# Idea Loop

`GAP → Mechanism Hypothesis → Method → Novelty Search → Reviewer Attack →
Revision → Meta Review`

Start with the strongest plausible formulation of the selected GAP. Identify the
failure mechanism before naming a module. Explain what information flow,
gradient path, optimization target, or decision process must change, why a simple
baseline cannot already solve it, and what result would falsify the mechanism.

Keep competing hypotheses alive until a discriminative test separates them.
When useful, consider M0 minimal, M1 moderate, and M2 expressive variants, but do
not generate three versions mechanically. Prefer the smallest version that tests
the claimed mechanism. Identify a strong simple baseline and an oracle/headroom
check where appropriate.

Search for prior work by mechanism, task, setting, and information availability.
Incremental ideas are acceptable when the difference is real, useful, and
supported; do not inflate them into theoretical novelty.

Review proceeds through attack, evidence-based defense or revision, and meta
review. Attack premises, causality, leakage, temporal availability, baseline
fairness, confounders, cost, and novelty. Concede unsupported claims. Meta review
chooses one of `PROCEED`, `PROCEED_WITH_MODIFICATIONS`,
`RETURN_TO_LITERATURE`, `SIMPLIFY`, or `PIVOT` based on unresolved
decision-critical risks.

