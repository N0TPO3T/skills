# Literature Extraction Gold Annotation

Use `research-agent eval literature create-set PROJECT --size 30` to select
verified, parsed, non-synthetic papers. The target is 30 papers initially and at
most 50 for the first benchmark version. The sampling requirements are recorded
in `benchmark.yaml`; selection still requires a human to check domain and
document-structure balance.

For each paper, export an editable template:

```bash
research-agent eval literature export-annotation PROJECT PAPER-ID --format yaml
```

Annotators must read the cited paper version, write only statements supported by
that version, and fill only locators they can verify. Never estimate page numbers.
Keep author-stated limitations separate from analyst-inferred limitations; the
latter are deliberately excluded from gold `limitations_claimed`. Record valid
paraphrases narrowly enough that they do not change the scientific claim.

Import completed labels and run the deterministic evaluation:

```bash
research-agent eval literature import-annotation PROJECT annotation.yaml
research-agent eval literature run PROJECT
research-agent eval literature report PROJECT
```

Synthetic fixtures validate evaluation code but do not count as measured
extraction quality. A capability with no human-labelled positive examples remains
disabled.

