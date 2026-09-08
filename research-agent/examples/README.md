# Synthetic example

[`example_project.yaml`](example_project.yaml) is illustrative configuration for
a fictional research project. It contains no real papers, project state,
results, repositories, credentials, or user paths.

Initialize a comparable local project with:

```bash
research-agent init example_reasoning \
  --direction "resource-aware test-time reasoning for language models"
research-agent doctor example_reasoning
research-agent run example_reasoning --live --dry-run
```

The runtime creates `project.yaml` and `state.json`; it does not automatically
import this example file. Use the `checkpoint_b_response` values when the
resource checkpoint requests constraints, adapting them to resources you
actually control.

