# Experiment Loop

`Hypothesis → Minimum Viable Experiment → Result → Diagnosis → Belief Update →
Next Experiment → Evidence`

Optimize expected decision-relevant information per cost, not probability of a
positive result. Respect the progression from L0 sanity checks through L1 MVE,
L2 core tests, L3 mechanism ablations, L4 generalization, and L5 final paper
evidence. Do not scale an absent L1 signal into L4.

Before a core experiment, reproduce or validate the strongest relevant baseline
with reported result, tolerance, variance, preprocessing, environment difference,
and diagnosis. Define the research question, intervention, controls, metric,
success criterion, falsification criterion, confounders, seeds, information
availability, train/eval differences, and resource estimate. Avoid leakage and
unavailable future information.

Only runner-produced artifacts establish that an experiment ran. Record command,
configuration, code revision, environment, stdout/stderr, metrics, timestamps,
and failures. Separate observation from interpretation and update hypothesis
status explicitly.

For positive results, rule out confounders and simpler explanations before
replication, ablation, or scaling. For negative or anomalous results, compare
implementation bugs, data/schema errors, alignment, optimization failure,
training budget, false hypotheses, subset effects, metrics, baseline unfairness,
noise, and hidden compute tradeoffs. For each, record evidence for/against,
probability, and the cheapest discriminative test; change one decision-critical
factor at a time.

Fix, modify, reject, or pivot according to evidence. Stop when the next test is
unlikely to change the decision relative to its cost, or a kill criterion is met.
Preserve experiment, diagnosis, belief-update, and decision ledgers, including
negative results.

