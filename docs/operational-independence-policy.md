# Operational Independence Policy v0.1-draft

Stato: **bozza software, non approvata scientificamente**. Owner richiesti per
l'approvazione: un biostatistico indipendente e un reviewer wet-lab. Questa policy
formalizza il confine fail-closed del PRD v6; non certifica che un esperimento sia
indipendente.

## 1. Decisione che la policy governa

Per ogni combinazione di fattore, contrasto, endpoint, popolazione e timepoint,
N-Truth distingue:

- `allocation_level`: unità alla quale viene assegnato un livello del fattore;
- `application_level`: unità sulla quale l'intervento viene materialmente applicato;
- `measurement_level`: unità sulla quale viene osservato l'endpoint;
- `independently_assigned`: fatto tri-state sull'indipendenza operativa
  dell'assegnazione;
- `independence_mechanism`: descrizione verificabile del meccanismo concreto;
- `experimental_unit` e `independent_n`: conclusioni derivate, mai campi di input
  liberi.

`allocation_level` è necessario ma non sufficiente. Un modello statistico, una
formula con effetti casuali o un grande numero di osservazioni non crea replica di
disegno mancante.

## 2. Matrice di autorizzazione

| Allocation | Stato indipendenza | Meccanismo | Output ammesso |
|---|---|---|---|
| noto | `TRUE` | presente e tracciato | EU candidata = allocation unit; `independent_n` solo da unità uniche e scope valido |
| noto | `TRUE` | assente | stato incompleto; EU e singolo `n` trattenuti |
| noto | `FALSE` | presente o assente | nessuna promozione automatica dell'allocation unit a EU indipendente |
| noto | `UNKNOWN` | non decisivo | rami condizionali finiti se enumerabili; altrimenti informazione insufficiente |
| ignoto | qualsiasi | qualsiasi | EU e `independent_n` null; domanda minima sull'allocation |
| fonti in conflitto | qualsiasi | qualsiasi | conflitto trattenuto; nessun override automatico |

Un output `DETERMINATE` richiede inoltre contrasto, endpoint, conteggio e target
coerenti, hard verifier valido e profilo supportato.

## 3. Evidenza accettabile e non accettabile

Una conferma può provenire da un evento procedurale localizzato, una tabella con
coordinate verificabili, un protocollo prospettico oppure una conferma umana con
ruolo, timestamp e audit. Allocation e indipendenza devono conservare evidence ID
distinti anche quando derivano dalla stessa fonte.

Non costituiscono prova autonoma:

- ID diversi, righe diverse, pozzetti diversi o una colonna di trattamento;
- le espressioni “esperimenti indipendenti” o “repliche biologiche” senza struttura;
- numero di donatori, preparazioni o piastre senza la relazione con l'evento di
  assegnazione;
- random effect, clustering dichiarato, `n` nel codice o risultato di un modello;
- confidence del parser o plausibilità biologica non confermata.

I fatti di origine `MODEL` rimangono candidati. Una conferma iniziale `USER` richiede
evidenza locale e ruolo; una correzione o adjudication richiede anche correction ID e
timestamp timezone-aware.

## 4. Conteggio e scope

`independent_n` conta unità di allocazione uniche nello scope, non righe, immagini,
cellule, campi o misure ripetute. Il conteggio deve indicare almeno fattore, contrasto,
gruppo/livello, endpoint, lifecycle e ogni condizione o timepoint rilevante. Il numero
di fonti biologiche resta in `biological_source_count`; `effective_n` è diagnostico e
non può sostituire `independent_n`.

Quando esistono relazioni uno-a-molti, pooling, split, pairing, ambiente condiviso o
time series, il sistema deve conservare la topologia e astenersi se il Core Profile
non la copre.

## 5. Correzione e audit

Una modifica umana:

1. applica una patch vincolata al record canonico;
2. conserva fonte, rationale, ruolo, timestamp, correction ID e checksum prima/dopo;
3. rigenera grafo, domande, regole e output entro il percorso deterministico;
4. non muta le fonti e non promuove automaticamente la correzione a gold;
5. deve poter essere annullata e riprodotta dal ledger append-only.

## 6. Gate di approvazione

Prima di congelare questa policy servono revisione field-by-field, almeno 10-20 bundle
reali esplorativi, casi negativi e controfattuali, verifica delle domande minime e
registrazione dei disaccordi. Ogni ampliamento di profilo richiede fixture, casi reali,
reviewer, versione e changelog.

