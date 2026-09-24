# Few-shot P0 baseline suite (B4)

Synthetic + realistic paraphrase fixtures for **contract/runtime** baseline of
Granite on P0 candidate-graph tasks.

- Gold targets are `CandidateGraphSet` candidate-only (no verdicts, no final n).
- Not used to train the rules engine.
- Not scientific validation; `scientific_validation_status` remains `NOT_STARTED`.
- Safe structural normalization may fill missing list fields as `[]`; it must not
  invent scientific content.

## Layout

- `cases.jsonl` — one JSON object per case (`split`: `demo` | `eval`)
- `manifest.json` — counts and ids

## Tasks covered

TASK_EVIDENCE, TASK_ENTITY_COUNT, TASK_FACTOR_ENDPOINT,
TASK_EXPLICIT_RELATIONS, TASK_CANDIDATE_GRAPH
