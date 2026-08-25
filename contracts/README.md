# Contract Packages (PRD v9 §0.4, §0.6, §20.2, §29.3)

I cinque manifest in questa directory sono i Contract Packages canonici v9:
`cp-sci.yaml`, `cp-epi.yaml`, `cp-data.yaml`, `cp-eval.yaml`, `cp-run.yaml`.

## Gerarchia di autorità (PRD §0.4)

1. Canonical Schema Registry;
2. Derivation Theory;
3. **Contract Packages e profilo** (questa directory);
4. Rulebook conforme;
5. esempi normativi;
6. testo informativo e snapshot storici.

I Contract Packages stanno sotto al registry e alla Derivation Theory: un CP non
può ridefinire enum, field name o semantica di derivazione, può solo dichiarare
owner, version, status, moduli, dipendenze ed evidenze. Gli esempi normativi e
il testo informativo stanno sotto ai CP e non possono ampliarne il contratto.

## Regola obbligatoria: owner/version/status/dipendenze espliciti

Per PRD §0.6 e §29.3 ogni pacchetto dichiara sempre:

- `owner`: ruolo bootstrap (PRD §29.1), mai nomi propri di persona;
- `version`: SemVer con suffisso `-alpha` finché lo status non è ACTIVE;
- `status`: `DRAFT` | `ACTIVE` | `DEPRECATED`;
- `dependencies`: CP da cui dipende, senza cicli;
- `gate`: condizione fail-closed della tabella §0.6 ("prima di derivare
  claim", "prima di annotazione/review", "prima di corpus/training",
  "prima di claim AI", "prima di runtime pubblico");
- `current_evidence`: path reali del repository che implementano ciascun
  modulo minimo. Un modulo privo di evidenza usa il marker `MISSING_EXPLICIT`
  (ammesso ma contabilizzato dal checker) e compare in `known_gaps`.

Non è obbligatorio creare un file fisico per ogni modulo (§0.6): è obbligatorio
che owner, version, status e dipendenze siano espliciti.

## Validazione

```
uv run python scripts/check_contract_packages.py
```

Il checker valida: YAML parseabile (subset deterministico del repo, oppure
PyYAML se disponibile), campi obbligatori presenti, path di `current_evidence`
esistenti (o marker `MISSING_EXPLICIT` contabilizzato), dipendenze acicliche.
La CI deve restare verde solo se nessun gap è silenzioso.
