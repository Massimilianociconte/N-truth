# Riconciliazione PRD v1 → PRD v3

**Data del checkpoint:** 1 agosto 2026<br>
**Fonte del checkpoint:** PRD v3 privato dell'autore, non distribuito nel repository<br>
**Specifica pubblica normativa:** [N-Truth Public Specification v0.1](public-specification-v0.1.md)<br>
**Stato:** audit implementativo del working tree; non è una validazione scientifica.

Questo documento conserva la storia della riconciliazione. Per implementazione,
contributi e review pubbliche fanno fede la specifica pubblica, gli schemi versionati
e i test eseguibili; non è necessario possedere il PDF sorgente.

## 1. Esito

Il PRD v3 non è un aggiornamento editoriale della v1: ridefinisce il prodotto come
programma a due track, amplia l'oggetto scientifico oltre la sola pseudoreplicazione e
stabilisce un percorso positivo per progettazione, revisione ed export.

Il working tree contiene gran parte della fondazione deterministica e i nuovi contratti
software. Non è tuttavia corretto dichiarare completa la v0.1: mancano fixture
canoniche complete e revisionate, casi reali/pubblici autorizzati, revisione esterna e
prova cross-platform su una revisione candidata. Tutti i risultati dipendenti da gold,
modello o validazione restano assenti.

## 2. Cambiamenti vincolanti

### 2.1 Obiettivo e roadmap

| Prima | PRD v3 | Conseguenza |
|---|---|---|
| Baseline deterministica trattata come centro del prodotto | Track A deterministica e Track B AI/corpus devono convergere | La v0.1 può essere manuale; la v1.0 richiede un parser AI valutato nel dominio dichiarato |
| Focus prevalente su unità e pseudoreplicazione | Piattaforma di ricostruzione/verifica del disegno | Schema, UI e report devono rappresentare disegno, target, alternative e provenance |
| Alert di rischio principalmente su pseudoreplicazione | Tre problemi scientifici distinti | Classi di alert separate, senza trasformare ogni limite in pseudoreplicazione |
| Audit retrospettivo dominante | Flusso prospettico, retrospettivo e annotativo | Necessari editor, Methods statement, checklist e record riutilizzabile |

### 2.2 Tre classi scientifiche

- `DESIGN_REPLICATION`: verifica se l'intervento/fattore è replicato su unità
  indipendenti.
- `ANALYTICAL_DEPENDENCE`: verifica se la correlazione tra osservazioni è rappresentata
  nell'analisi.
- `INFERENCE_SCOPE`: verifica se il claim supera la popolazione o il livello replicati.

Un modello gerarchico può gestire dipendenza analitica ma non creare replicazione
mancante. Più colture dallo stesso donatore possono sostenere un claim sulle colture di
quel donatore ma non automaticamente la variabilità tra donatori.

### 2.3 Allocazione e applicazione

La v3 rende obbligatoria la separazione tra:

- `allocation_level`: unità alla quale i livelli possono essere assegnati
  indipendentemente;
- `application_level`: unità sulla quale la procedura è materialmente eseguita.

I campi possono divergere e non devono essere fusi. La compatibilità legacy con
`assignment_level` deve puntare all'allocazione, non all'applicazione.

### 2.4 Contrasto, target ed estimando

Il contrasto può coinvolgere più fattori e livelli. L'estimando minimo deve includere:

- endpoint;
- misura dell'effetto;
- popolazione o insieme di unità target;
- livello di generalizzazione;
- fattori;
- eventuale tempo o condizione.

`InferenceTarget` ed `Estimand` sono distinti: il primo formalizza domanda/claim e
popolazione; il secondo formalizza l'effetto target. Entrambi restano conservativi e
non autorizzano scelta automatica di test, formula o power analysis.

### 2.5 Grafo ed evidenza

Il vocabolario minimo v3 aggiunge entità biologiche, processing/observation/design/
inferential/analysis/evidence objects e relazioni per splitting, pooling, pairing,
blocking, crossing, repeated measures, allocazione, applicazione, gruppi, esclusioni e
clustering dichiarato.

Le evidenze sono classificate come `STRUCTURAL_FACT`, `AUTHOR_ASSERTION`,
`SAMPLE_METADATA`, `STATISTICAL_CODE`, `USER_CONFIRMATION`, `MODEL_INFERENCE`,
`DERIVED_FACT` o `CONFLICTING_EVIDENCE`. “Independent experiments” è
un'autovalutazione, non prova conclusiva.

### 2.6 n e determinabilità

La v3 vieta un singolo `n` globale quando esistono fattori o endpoint differenti.
`n_declared`, `n_observational` e `n_independent` restano distinti; allocato e
analizzato servono a rappresentare attrition, pooling e perdita d'identità.

Se un fatto cambia il risultato, il motore produce:

```json
{
  "conditional_on": "cultures_are_independent_preparations",
  "if_confirmed": {"control": 4, "drug": 4},
  "if_rejected": {"control": 1, "drug": 1},
  "question": "Le colture derivano da preparazioni biologiche indipendenti?"
}
```

L'assenza di fattore/contrasto, allocazione, unità, conteggio, indipendenza, endpoint o
target necessario porta a stato indeterminato; non viene usato un fallback numerico.

### 2.7 Codice statistico e parser AI

Script R/Python/R Markdown sono input read-only. Possono sostenere
`declared_clustering` come evidenza silver, ma non dimostrare allocazione o
randomizzazione.

Il parser AI deve avere un confine JSON stabile, output vincolato, candidate fact con
evidence/confidence/alternative e nessun verdetto finale. Le conseguenze del motore
deterministico espongono premesse e `rule_id`, non una probabilità separata.

### 2.8 Percorso positivo e DRIVER

Il report non deve limitarsi agli errori. Deve includere sintesi, grafo,
fattori/allocazioni, endpoint/contrasti/estimandi, tabella di `n`, percorso verde,
alert per classe, domande decisive, opzioni analitiche candidate, limiti e provenance.

Il mapping a DRIVER è informativo e indipendente. N-Truth non è un prodotto NC3Rs, non
certifica conformità e non deve suggerire endorsement.

### 2.9 Dati, licenze e governance

Il PRD v3 distingue Rule Fixtures, Parser Gold Corpus, silver/weak supervision,
synthetic graph-to-text ed external challenge. Gli usi di ogni asset sono granulari;
analizzare localmente non autorizza training, condivisione o redistribuzione.

Gli snapshot devono registrare versioni, checksum, governance e gruppi anti-leakage.
ID campione, nomi file e metadata richiedono controllo privacy locale prima di
export/share.

## 3. Mappatura sul working tree

Le voci “presente” indicano codice o documentazione nel working tree; non equivalgono
a review esterna o release.

| Area v3 | Stato | Evidenza nel repository | Gap residuo |
|---|---|---|---|
| Schema/grafo tipizzato | presente | `packages/ntruth/schemas/`, `graph/` | review scientifica e stabilizzazione su casi reali |
| Allocation/application separate | presente | schema, compiler, grafo e UI | validazione su disegni reali multifattoriali |
| Estimando minimo | presente | schema e handoff | copertura fixture/corpus e review biostatistica |
| n condizionale | presente | scenari nel resolver/report | 30–60 fixture complete e revisionate |
| Tre classi di alert | implementazione presente | 10 design, 17 analytical, 5 scope; tutte le regole dichiarano `alert_class` e la mappatura è congelata nei test | mapping candidato da revisionare scientificamente |
| Evidence types/provenance | presente | schema, estrattori e parser contract | benchmark evidence classification assente |
| R/Python never-execute | presente | parser code artifact | casi reali/licenze e security review |
| Contratto parser AI | presente | `packages/ntruth/parser_ai/`; schemi input/output esportati, inclusi nella RO-Crate e usati dalla corsia MLX | integrazione nel flusso UI, few-shot su casi reali e modello valutato assenti |
| Editor/correzioni | presente | app locale, patch append-only, undo/redo | studio utente e workflow gold non validati |
| Percorso positivo | presente | Methods, n table, livelli epistemici, checklist | review linguistica/scientifica e golden test estesi |
| JSON/YAML/JSON-LD | presente | reporting/export; RO-Crate non estende Apache-2.0 a dataset/input | interoperabilità REMBI/ISA non dichiarabile come completa |
| Governance/lineage/privacy | presente nel flusso standard | privacy scan/readiness, API e CLI fail-closed; nessun transfer | generatore di derivati/pacchetti, token/audit persistente e verifica esterna dell'autenticità restano assenti; `write_all` senza Document IR non è readiness |
| Rule fixtures | parziale | 128 scenari harness + 12 regressioni | non equivalgono a 30–60 casi completi expert-reviewed |
| Experiment Bundle reali/pubblici | assente | nessun manifest reale | almeno 10 per deliverable iniziale; 20 disegni stabili prima del training |
| Gold/IAA/human ceiling | assente | solo template | 30 calibration + pilot 150–250 doppio/adjudicato |
| AI/ML | pipeline pronta, training scientifico assente | preparazione governata, profilo MLX fissato, QLoRA/checkpoint/resume, scoring, calibrazione ed export; smoke runtime sintetico | gold, baseline su casi reali, fine-tuning scientifico, risk-coverage misurata e model card finale |
| External validation | assente | protocollo in bozza | challenge chiuso, laboratori unseen e metriche congelate |

## 4. Interpretazione corretta delle fixture correnti

Il repository contiene due oggetti diversi:

1. **12 regressioni scientifiche sintetiche:** congelano comportamenti storici e
   intercettano cambiamenti semantici;
2. **128 scenari di contratto delle regole:** il test harness esercita quattro esiti
   per ciascuna delle 32 regole.

La matrice dimostra copertura eseguibile delle regole, non che esistano 128 disegni
scientifici indipendenti e revisionati. Per soddisfare PRD v3 §14.2/F.1 ogni fixture
canonica deve avere grafo completo, output, eccezione, controesempio, riferimento e
review. Il catalogo machine-readable registra esplicitamente questa distinzione.

## 5. Gate aperti prima del training

Il training resta bloccato finché non sono vere tutte le condizioni:

- [ ] almeno venti disegni reali rappresentabili senza modifiche sostanziali allo schema;
- [ ] regole principali revisionate e testate;
- [ ] baseline few-shot capace di produrre payload validi rispetto al contratto;
- [ ] guideline capace di separare fatti, assertion e inferenze;
- [ ] protocollo del pilot congelato;
- [ ] licenze e autorizzazioni registrate;
- [ ] train/validation/test/external separabili senza leakage.

Questi gate non eliminano la Track B: impediscono soltanto di addestrare su un target
instabile o non autorizzato.

## 6. Primo percorso umano raccomandato

1. Far revisionare definizioni, estimando, tre classi e dieci casi canonici da un
   wet-lab reviewer e un biostatistico.
2. Completare 30–60 fixture canoniche con controesempi e riferimenti.
3. Raccogliere dieci Experiment Bundle reali/pubblici con manifest e privacy check.
4. Eseguire il calibration set di 30 casi in doppio e correggere schema/guideline.
5. Congelare protocollo e redirect criteria.
6. Avviare il pilot 150–250 bundle, misurare agreement e human ceiling.
7. Solo dopo, eseguire baseline few-shot e decidere se/come procedere al fine-tuning.

La checklist operativa e il modulo di review sono rispettivamente in
`docs/first-human-steps-checklist.md` e `docs/external-review-template.md`.
