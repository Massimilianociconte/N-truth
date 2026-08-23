# Registro delle transizioni audited dei pin evaluator

Ogni riga documenta una transizione di identita ingegneristica della chiusura
evaluator pinnata (SRR-V8-024/SRR-V8-027). Una transizione e un cambio di
identita, non una validazione scientifica: Theory, Rulebook e la semantica delle
regole restano identici salvo indicazione esplicita.

## 2026-08-23 — registry 0.1.0 → 0.1.1 (hardening EvidenceSpan)

- **Trigger:** port dell'hardening `EvidenceSpan.start/end ge=0` dal lineage
  baseline (commit `eed54f1`) sul ramo canonico. Il cambio appartiene alla
  chiusura di identita degli schemi (`schemas/core.py`) e invalida i pin
  derivati.
- **Scope:** `schemas/core.py` (solo vincoli di dominio sugli offset);
  nessuna modifica a Theory, Rulebook, semantica delle regole o fixture.
- **Artefatti:** `theories/reviewed-evaluator-registry-0.1.1.json` (nuovo;
  0.1.0 rimosso dall'albero, preservato nella storia git);
  `rulesets/ntruth-v8-core-0.1.0.json` (solo cross-reference
  `evaluator_registry_version/checksum` + `declared_checksum` ricalcolato);
  costanti `_REVIEWED_*` in `derivation_theory/runtime.py`.
- **Digest:** closure checksum `4244d63b4c852110d5b67fc007db9ef9679f8631f3558989c41a8901a58367e2`;
  registry declared `fb0be8b34e9f736d5fbe1a30f9c5151b701d3847880cb72bef3dd7f892f4b91f`;
  rulebook declared `dc10b6a53cc754b2be1263a83561dcb1c1faf555b80e61013a4dd45e28761c97`;
  theory declared invariato (`aa376398…`).
- **Esito:** `verify_runtime_bundle` PASS; suite completa verde.
- **Non coperto:** alcuna pretesa di approvazione scientifica; i blocker
  SRR restano aperti verso i reviewer esterni.
