# SourceData → entity_roles label map (v0.1.0)

## Source

- Dataset: EMBO/SourceData token classification v2.0.3
- Channels: NER (`entity_tags`) + ROLES_MULTI (`role_tags`) after Workstream B alignment
- Scheme: BIO

## Entity types (NER)

| Tag type | Meaning (SourceData) | Canonical |
|----------|----------------------|-----------|
| GENEPROD | gene/protein product | GENEPROD |
| ORGANISM | organism | ORGANISM |
| TISSUE | tissue | TISSUE |
| CELL_LINE | cell line | CELL_LINE |
| CELL_TYPE | cell type | CELL_TYPE |
| DISEASE | disease | DISEASE |
| SMALL_MOLECULE | small molecule | SMALL_MOLECULE |
| SUBCELLULAR | subcellular localization | SUBCELLULAR |
| EXP_ASSAY | experimental assay | EXP_ASSAY |

## Role types (ROLES_MULTI)

| Tag type | Meaning | Canonical |
|----------|---------|-----------|
| CONTROLLED_VAR | controlled / intervention variable | CONTROLLED_VAR |
| MEASURED_VAR | measured variable | MEASURED_VAR |

## Policy

- Prefixes `B-` / `I-` preserved.
- `O` is outside entity/role.
- Unknown tags → record excluded (`UNMAPPED_LABEL`), never implicit map.
- `authority_level=AUXILIARY`; never N-Truth experimental-unit / n / verdict gold.
- Machine map: `packages/ntruth/task_corpora/label_maps/sourcedata_entity_roles.json`
