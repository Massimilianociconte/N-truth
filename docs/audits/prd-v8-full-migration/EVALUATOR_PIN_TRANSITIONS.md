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
- **Anchor repository-truth:** il descrittore `rulebook-conformance` della mappa
  `prd-v8-current-to-target.yaml` e' stato ri-ancorato (`4567fa88…`) con la
  stessa procedura audited: cambio di identita dei percorsi, non di semantica.
- **Non coperto:** alcuna pretesa di approvazione scientifica; i blocker
  SRR restano aperti verso i reviewer esterni.

## 2026-08-25 — registry 0.1.1 → 0.1.2 (ScenarioCompleteness v9)

- **Trigger:** implementazione della violazione v9 `ScenarioCompleteness`
  (PRD §0.3/§AI.3): rimozione di `EXHAUSTIVE_WITHIN_PROFILE` dal vocabolario
  scrivibile in `packages/ntruth/schemas/coverage.py` e introduzione della terna
  `COMPLETE_UNDER_DECLARED_ASSUMPTION_SET` / `INCOMPLETE_KNOWN` /
  `UNKNOWN_COMPLETENESS` con assumption set versionato e finalizzato più
  `counterexample_search_status` obbligatori per il claim di completezza.
  `coverage.py` appartiene alla closure di dipendenza dell'evaluator pinnato
  (`contract_sources`/`contract_schemas`), quindi il cambio invalida tutti i pin
  derivati.
- **Scope:** solo contratti di copertura; nessuna modifica a Theory, Rulebook
  (regole), semantica delle regole o fixture. L'ADEQUACY pin
  (`rules/v8_engine.py`) resta invariato byte-per-byte.
- **Artefatti:** `theories/reviewed-evaluator-registry-0.1.2.json` (nuovo;
  0.1.1 rimosso dall'albero, preservato nella storia git);
  `rulesets/ntruth-v8-core-0.1.0.json` (solo cross-reference
  `evaluator_registry_version/checksum` + `declared_checksum` ricalcolato);
  costanti `_REVIEWED_*` in `derivation_theory/runtime.py`; snapshot schemi
  kernel rigenerato; descrittore `rulebook-conformance` ri-ancorato nella mappa
  corrente-target con la stessa procedura audited.
- **Digest:** closure checksum `c7078797e06dbed3fd97d39aaddce73cf1af00d12c257618302e0b21b8fffcc3`;
  registry declared `124b404e4d42eeb9ff48f52bbf8c39ecc5538fdc9955f379405f41206c22dcac`
  → `ffc5216118c460cd66cef1c0c68e735d9b0b50faa5c6f9e5f5ba8f3efdd31dc8`;
  rulebook declared `8a25918b3c1ce07bcf85e445b0690fe5d1c6ec9a1cafb944b35ad123c6ae3d18`
  → `21e1da7294ec392646ef29aa3cb3602f50f363b046cf6ab3de29f1cf44e28d68`;
  theory declared invariato (`aa376398…`); i sette pin DERIVATION cambiano
  implementation digest (DT-A `87940ff2…` → `29aef89d…`, DT-B `8f1c9afc…` →
  `d6ecc46d…`, DT-C `cddcb968…` → `6969aa95…`, DT-D `de7537f7…` → `d8266580…`,
  DT-E `5de518e5…` → `69a86ef7…`, DT-F `38e3e98f…` → `406deda5…`, DT-G
  `82c2c3e6…` → `5fc4c940…`), l'ADEQUACY pin è invariato (`287691ed…`).
- **Compatibilità di lettura:** i payload legacy `EXHAUSTIVE_WITHIN_PROFILE`
  restano deserializzabili tramite adapter fail-closed: mappati a
  `COMPLETE_UNDER_DECLARED_ASSUMPTION_SET` solo se l'assumption set completo è
  dichiarato, altrimenti a `INCOMPLETE_KNOWN`. I writer v9 non emettono mai il
  token legacy (rimosso dall'enum).
- **Esito:** `verify_runtime_bundle` PASS; suite completa verde.
- **Non coperto:** alcuna pretesa di approvazione scientifica; i blocker SRR
  (incluso SRR-V8-008) restano aperti verso i reviewer esterni.

## 2026-08-27 — SRR-V8-021, passo meccanico parziale: primo pin del content hash del crosswalk DRIVER→ARRIVE (sezione separata dalla chiusura evaluator; nessuna transizione di pin evaluator)

- **Trigger:** primo pin meccanico (custodia) del content hash dello snapshot
  strutturato `CW-DRIVER-SNAPSHOT-001` in `docs/driver-arrive-crosswalk.md`,
  eseguito con il meccanismo fail-closed `ExternalReferenceFreeze`
  (`packages/ntruth/conformance/external_references.py`), che conserva il
  blocker `SRR-V8-021` pinned. Non è una transizione di identita della
  chiusura evaluator: Theory, Rulebook e i pin derivati restano invariati.
- **Scope:** solo custodia meccanica del reference freeze; nessun claim di
  conformità DRIVER/ARRIVE e nessun cambio di semantica delle regole.
- **Artefatti:** `data_manifests/driver-arrive-crosswalk-freeze.json` (nuovo;
  record interno validato con `ExternalReferenceFreeze.model_validate`, ruolo
  custode `repository-maintainer`, `rights_closure_external: true`);
  `docs/driver-arrive-crosswalk.md` (solo riga di stato, paragrafo §5 e campo
  `content_hash` dello snapshot; righe di mapping non toccate).
- **Digest:** checksum canonico SHA-256 del materiale mappato
  `4afcfb5b0e47ab5eee7523850685d4e35697f7aaa8f4099378a0b2419e939eb6`
  (canon `json.dumps(..., ensure_ascii=False, sort_keys=True,
  separators=(",",":"))` sul blocco snapshot escluso il campo `content_hash`;
  stesso schema di `ntruth.derivation_theory.loader.canonical_checksum`);
  freeze record `declared_checksum`
  `995894e671fc3bdd99fe2339ecfa761a6e703bc1e5c712a922186a338f957f61`.
- **Esito:** record valido secondo il modulo di conformance; pin registrato.
- **Non coperto:** approvazione scientifica dello snapshot, review del
  Methodology lead, chiusura dei diritti e review indipendente (SRR-V8-021
  resta aperta verso reviewer esterni), suite di mapping claim-grade: la voce
  rimane `snapshot non approvato`, nessuna promozione a `implements`.
