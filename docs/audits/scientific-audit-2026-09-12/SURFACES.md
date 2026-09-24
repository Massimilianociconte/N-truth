# Audit superfici N-Truth (read-only, 2026-09-12)

Codice non modificato. Riproduzioni eseguite con `.venv/bin/python`; parser PDF verificato con oggetti mock e griglie in memoria, senza aprire alcun PDF locale.

## Findings confermati

### S1 — P1/P2: collisione degli header tabellari cancella celle senza warning
File `packages/ntruth/parsers/tabular.py:217-227`, utilizzo distruttivo a `:203-208`.
`_unique_headers` conta i nomi originali ma non riserva i nomi generati. Header `animal,animal,animal_1` genera `['animal','animal_1','animal_1']`. La riga `A,B,C` diventa `{'animal':'A','animal_1':'C'}`: B sparisce, status OK e warning vuoti. Il problema vale CSV D0 e XLSX extended perché condividono `_build_table`; può distruggere identificatori/categorie utilizzati nella ricostruzione delle unità. Gli header duplicati non sono rifiutati dal safety check CSV. Anche `pdf.py:180-190` ha lo stesso difetto con `x,x,x (2)`.
Repro: `_build_table('sample', iter([['animal','animal','animal_1'],['A','B','C']]), RawDocument(parser='csv'))`.
Correzione: allocare un insieme globale dei nomi già assegnati e cercare un suffisso libero; test collisioni tra nomi originali e generati, preservando tutte le celle.

### S2 — P2: il PDF perde righe sopra il limite senza dichiarare output parziale
File `packages/ntruth/parsers/pdf.py:165-176`.
`rows` viene ridotto a `MAX_PDF_TABLE_ROWS + 1` prima del controllo `len(rows)-1 > MAX_PDF_TABLE_ROWS`: la condizione del warning non può mai essere vera. Repro `_grid_to_table([['id','n']]+[[str(i),'1'] for i in range(2002)],'t')` restituisce 2000 righe, warnings `[]`. Anche il limite colonne usa `min(...,128)` senza warning. Il consumatore riceve una tabella incompleta apparentemente ordinaria; conteggi e provenance possono risultare incompleti. Superficie extended sperimentale, non wizard core.
Correzione: conservare dimensioni originali, segnalare troncamenti e propagare status PARTIAL al documento.

### S3 — P2: PDF misto con pagina senza testo resta OK se la media globale supera 200 caratteri
File `packages/ntruth/parsers/pdf.py:74-96`.
L'estrazione vuota per una singola pagina non viene segnalata; la degradazione dipende esclusivamente dalla densità media del documento. Repro con PdfReader mock a due pagine (`'Methods data '*100`, `''`) restituisce status `ok`, unico warning relativo a pdfplumber mock non installato. Una pagina scansionata contenente metodi/unità può sparire senza indicazione della necessità di OCR. Le eccezioni generano warning, ma stringa vuota normale no. Non si può distinguere automaticamente una pagina bianca da una scansione sulla sola stringa; serve classificazione pagina e warning conservativo, con mapping pagina/evidenza.

### S4 — P2/P3: comando reality gate README non esiste
`README.md:150` documenta `uv run ntruth reality-gate`; `packages/ntruth/cli/main.py:666` registra solamente `quick-design reality-gate`.
Repro CliRunner().invoke(app,['reality-gate']) => exit 2, `No such command 'reality-gate'`. Uso corretto: `ntruth quick-design reality-gate` (oppure alias top-level da implementare). Il quickstart quindi non verifica lo stato HOLD come promesso.

## Mappa delle superfici effettive

- README: desktop Quick Design workflow principale, JSON CLI dichiarato esplicitamente RAW_AUTHOR_ASSERTED; storico ingest qualificato analyze-v7.
- CLI `analyze` e API `/analyze`/`/v1/analyze`: percorso raw canonico bloccato con scientific review required; non è un equivalente funzionale del wizard. API blocco esplicito `app.py:681-700`.
- API `/v8/quick-design`: submission raw validata come author asserted, output contract guided_confirmation false (`app.py:923-958`).
- API `/v8/quick-design/build-submission`: preview e conferma guidata atomica (`:960-980`); UI QuickDesignWizard template `simple_cell_culture` fisso e disabled, disponibilità limitata a questo template.
- API `/v1/prospective/d0/compile`: superficie D0 distinta con limite body; `/v1/prospective/plan-execution` persistenza e gold.
- Ingest storico: D0 solo txt/md/csv; PDF/DOCX/XLSX/JATS/codice richiedono extended_experimental. Quindi S2/S3 sono debito reale della corsia sperimentale e non impediscono da soli l'esecuzione del wizard.
- API entrypoint vincolato a 127.0.0.1, TrustedHost 127.0.0.1/localhost; nessuna autenticazione, coerente con README. Non qualificare automaticamente come vulnerabilità remota.
- Ingest: controlli estensione/firma, budget archivi decompressi, path containment e symlink; codici R/Python trattati come testo. Reporting storico Jinja autoescape attivo. Endpoint report con containment nei run attivi. Questi controlli riducono rischi concreti rispetto a una superficie arbitraria.

## Limiti

Esame mirato di API/CLI/parser/ingest e collegamento UI; non eseguita suite intera né audit di ogni percorso React/report. Nessuna dichiarazione di sicurezza completa. I findings sono separati dalle limitazioni intenzionali di readiness scientifica. Non sono stati scaricati documenti né modificati sorgenti/dati.
