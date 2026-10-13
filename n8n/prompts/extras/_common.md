# extras – common part

Every extras prompt below is a system prompt for one LLM call per block (docs/result-schema.md,
section 5). Each block is independent: it gets the whole cleaned transcript and the final digest
structure, returns one JSON object, and is validated on its own. Placeholders `<<...>>` are filled
by the workflow. This file is documentation; the workflow reads the per-block files, which repeat
the shared rules so that each prompt is self-contained.

Shared input format (user message):

```
STRUCTURE
[0.0–147.6] Title of part 1
[147.6–504.5] Title of part 2

TRANSCRIPT
[7.5] First cleaned paragraph…
[41.2] Second paragraph…
```

Shared rules: timestamps are copied from the input, never invented; strings are plain text
without markdown; output in `<<OUTPUT_LANGUAGE>>` unless a field is defined as verbatim; sponsor
segments, channel greetings and calls to subscribe are not content and produce nothing.
