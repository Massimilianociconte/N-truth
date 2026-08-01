# N-Truth — Annotation Guideline v0.1

**Stato:** bozza operativa riallineata al PRD v3; non approvata e non gold.<br>
**Owner richiesti:** annotation lead, wet-lab reviewer e adjudicator biostatistico.
**Fonte normativa:** PRD v3 §§7–10, 14, 16–18 e Appendici A–D.

Questa guideline deve essere revisionata prima del pilot. Non è consentito adattarla
retroattivamente per migliorare l'accordo o le prestazioni di un modello.

## 1. Unità di annotazione

L'unità dati è l'**Experiment Bundle**; l'unità scientifica annotata è un
**ExperimentBlock**, cioè un insieme coerente di Methods, caption, statistica,
sample sheet e metadata riferiti a uno specifico disegno o contrasto. Un articolo può
contenere più blocchi e non riceve una singola label globale.

Per ogni blocco, nell'ordine:

1. identificare domanda/claim o dichiararne l'assenza;
2. marcare evidence span e classificarne il tipo;
3. identificare unità, fattori, livelli, gruppi, endpoint e conteggi;
4. annotare relazioni, coreference e provenance;
5. specificare separatamente `allocation_level` e `application_level` per fattore;
6. definire contrasti e, se determinabile, estimando e target inferenziale;
7. distinguere unità biologica, sperimentale, osservazionale e analitica;
8. registrare `n` dichiarato, allocato, analizzato, osservazionale e indipendente per
   gruppo/contrasto/endpoint;
9. classificare la determinabilità e conservare grafi/scenari alternativi;
10. formulare la domanda minima che discrimina le alternative;
11. assegnare eventuali alert alle tre classi scientifiche, senza confonderle;
12. registrare rationale, tempo, difficoltà e, separatamente, adjudication.

## 2. Definizioni vincolanti

| Termine | Definizione operativa |
|---|---|
| Unità biologica | Entità biologica di interesse o origine del materiale: donatore, animale, linea, coltura primaria, organoide, tessuto o altra entità definita dal dominio. |
| **Unità sperimentale** | Più piccola unità alla quale i livelli di un fattore possono essere assegnati indipendentemente, per il contrasto considerato. Non è globale. |
| Unità osservazionale | Entità sulla quale viene effettuata la misura. |
| Unità analitica | Riga o aggregato effettivamente inserito nel modello statistico. |
| Replica biologica | Istanza indipendente dell'unità biologica pertinente alla domanda e alla popolazione di inferenza; non è provata dalla sola etichetta dell'autore. |
| Replica tecnica / sottocampione | Misura o lavorazione ripetuta sullo stesso materiale; non incrementa automaticamente le unità sperimentali. |
| `allocation_level` | Livello al quale i valori del fattore possono essere assegnati indipendentemente. |
| `application_level` | Livello sul quale la procedura viene materialmente applicata. Può differire dall'allocazione. |
| Contrasto | Livelli di uno o più fattori che vengono confrontati per uno specifico endpoint. |
| Estimando minimo | Endpoint, misura dell'effetto, popolazione o insieme di unità target, livello di generalizzazione, fattori ed eventuale tempo/condizione. |
| `n_declared` | Numero associato dagli autori a un risultato, con entità e posizione. |
| `n_observational` | Numero di osservazioni o misure. |
| `n_independent` | Istanze dell'unità sperimentale pertinenti a fattore e contrasto, eventualmente condizionali. |

### 2.1 Principio per fattore

Lo stesso esperimento può avere unità diverse: genotipo allocato all'animale, farmaco
allocato al pozzetto e tempo come misura ripetuta. Si annotano mappe per fattore,
contrasto ed endpoint; non si sceglie una sola unità per il blocco.

### 2.2 Allocazione non è applicazione

I due campi non vanno copiati automaticamente. Se una procedura è materialmente
eseguita sul campione ma il trattamento era già stato assegnato alla sorgente, si
conservano entrambi i livelli. Se uno dei due non è riportato, resta `null` e genera una
domanda.

## 3. Evidenza e provenance

Ogni candidate fact non banale richiede almeno un riferimento stand-off alla fonte.

| Tipo | Trattamento |
|---|---|
| `STRUCTURAL_FACT` | Può sostenere nodi e archi strutturali se lo span è esplicito. |
| `AUTHOR_ASSERTION` | Genera un candidato o una domanda; non prova da sola indipendenza. |
| `SAMPLE_METADATA` | Evidenza strutturata ad alta priorità se coerente e con provenance. |
| `STATISTICAL_CODE` | Evidenza silver del clustering dichiarato; non determina l'allocazione. |
| `USER_CONFIRMATION` | Priorità elevata, identità/ruolo e audit obbligatori. |
| `MODEL_INFERENCE` | Candidato con confidenza, alternative e versione del modello. |
| `DERIVED_FACT` | Conseguenza deterministica con `rule_id` e precondizioni, senza “probabilità” propria. |
| `CONFLICTING_EVIDENCE` | Fonti incompatibili; blocca il verdetto finché non risolte. |

La provenance minima include documento/versione, sezione o pagina, offset o cella,
testo originale, metodo di estrazione, correzione, timestamp e versioni applicabili.

Espressioni come “independent experiments”, “biological replicates” o “n represents
independent samples” restano `AUTHOR_ASSERTION`. L'annotatore deve cercare origine,
allocazione, preparazioni e conteggi.

## 4. Procedura

### Passo 1 — Intake del Bundle

Registrare file e ruolo: Methods, caption, schema gruppi, sample sheet, mapping
file-campione, codice statistico ed eventuale risposta esperta. Verificare manifest,
usi consentiti e presenza di identificatori prima di condividere o annotare.

### Passo 2 — Domanda e oggetti inferenziali

Annotare:

- domanda o claim;
- fattori e livelli;
- gruppi e contrasto;
- endpoint;
- popolazione o unità target e livello di generalizzazione;
- misura dell'effetto desiderata;
- eventuale tempo o condizione.

Non dedurre un estimando da una formula statistica. Se una componente decisiva manca,
classificare la determinabilità e formulare la domanda minima.

### Passo 3 — Unità e relazioni

Usare span minimi completi. Annotare soltanto relazioni dichiarate o dimostrate dai
metadata (`nested_in`, `derived_from`, `split_from`, `pooled_from`, `paired_with`,
`matched_with`, `blocked_by`, `crossed_with`, `same_source_as`,
`repeated_measure_of`, `allocated_to`, `applied_to`, `measured_on`,
`belongs_to_group`, `excluded_from`, `supports`, `contradicts`,
`declares_clustering`).

ID differenti non dimostrano indipendenza. I termini generici `replicate`, `sample` o
`experiment` non diventano tipi del grafo senza definizione operativa.

### Passo 4 — Mappa di unità e n

Per ogni scope fattore × contrasto × endpoint × gruppo, quando applicabile:

```text
unità biologica       : ...
allocation_level      : ... | null
application_level     : ... | null
unità sperimentale    : ... | null
unità osservazionale  : ... | null
unità analitica       : ... | null
n dichiarato          : ... | null
n allocato            : ... | null
n analizzato          : ... | null
n osservazionale      : ... | null
n indipendente        : ... | null
determinabilità       : DETERMINATE | MULTIPLE_PLAUSIBLE_GRAPHS |
                       CONFLICTING_INFORMATION | INDETERMINATE
```

Un `null` motivato non viene sostituito con un numero vicino. Se l'indipendenza cambia
in base a un fatto non confermato, annotare `conditional_on`, valori
`if_confirmed`/`if_rejected`, domanda ed evidenze.

### Passo 5 — Tre valutazioni distinte

| Classe | Cosa si valuta | Esempio |
|---|---|---|
| `DESIGN_REPLICATION` | Replicazione indipendente dell'intervento | un trattamento applicato a una sola piastra |
| `ANALYTICAL_DEPENDENCE` | Dipendenze tra osservazioni nell'analisi | cellule annidate nei pozzetti |
| `INFERENCE_SCOPE` | Compatibilità tra claim e popolazione replicata | una sola linea usata per generalizzare a più linee |

La severità è un asse separato e dipende da certezza dei fatti, impatto sul contrasto,
correggibilità e confondimento. Un mixed model può gestire una dipendenza analitica ma
non creare replicazione mancante. Un limite di generalizzazione non deve essere
rinominato pseudoreplicazione.

### Passo 6 — Alternative, domanda e rationale

Quando esistono più grafi plausibili, conservarli entrambi. La domanda deve chiedere
il singolo fatto che cambia maggiormente unità, `n` o portata dell'inferenza. Il
rationale di adjudication è breve, ancorato alle evidenze e separato
dall'annotazione originaria.

## 5. Controllo di qualità e agreement

### Calibration set

- 30 casi non conteggiati nel test;
- annotazione indipendente da profilo wet-lab e statistico;
- analisi degli errori dello schema e revisione della guideline;
- nessun fine-tuning sul materiale congelato come test.

### Feasibility pilot

- 150–250 Experiment Bundle;
- 100% doppia annotazione;
- adjudication di tutti i disaccordi;
- guideline versionata e decisioni motivate.

Riportare separatamente accordo sui tipi di unità, `allocation_level`,
determinabilità, archi/grafo e differenze biologo-biostatistico. Cohen κ è adatta solo
a categorie fisse; per grafi usare F1 su archi, graph edit distance o altre misure
predefinite nel protocollo. L'IAA si misura prima dell'adjudication.

I criteri di redirect, le metriche e le soglie devono essere congelati prima di aprire
il test. Le soglie citate nel PRD sono decisioni di programma, non risultati N-Truth.

## 6. Regole di condotta

- Annotare ciò che le fonti sostengono, non ciò che è probabile nel dominio.
- Non correggere silenziosamente il disegno degli autori.
- Non usare linguaggio accusatorio o pubblicare giudizi automatici su autori/paper.
- Non promuovere output AI o correzioni utente a gold senza review e adjudication.
- Non usare un asset oltre gli usi autorizzati nel suo record di governance.
- Registrare il tempo e la difficoltà: il pilot deve misurare il carico reale.

## 7. Gate prima dell'uso

Questa bozza diventa operativa soltanto dopo:

- [ ] revisione delle definizioni da wet-lab e biostatistico indipendenti;
- [ ] prova su almeno dieci casi canonici con disagreement log;
- [ ] approvazione dello schema delle evidenze e della determinabilità;
- [ ] protocollo del calibration set congelato;
- [ ] template di adjudication e regole di accesso ai dati approvati.

Il passo successivo non è il training: è verificare che persone competenti riescano a
rappresentare lo stesso disegno nello stesso modo e documentare dove non concordano.
