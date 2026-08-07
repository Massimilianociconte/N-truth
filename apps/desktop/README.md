# Desktop application

La UI React/Vite è la superficie locale di N-Truth. La modalità primaria è ora il wizard
prospettico D0 del PRD v6; il workspace retrospettivo rimane disponibile per import, revisione di
`ExperimentBlock`, evidenza sincronizzata, correzioni append-only ed export della sessione.

## Avvio locale

Requisiti: Node.js `>=20.19` e pnpm `11.9.0` (la versione è fissata in `package.json`).

```bash
cd apps/desktop
pnpm install --frozen-lockfile
pnpm dev
```

Vite ascolta esclusivamente su `http://127.0.0.1:5173/app/` e inoltra `/v1` e `/health` a
`http://127.0.0.1:8765`. In assenza dell'API la UI resta utilizzabile con dati sintetici
esplicitamente marcati come demo.

## Percorso prospettico D0

La voce iniziale **Progettazione D0** applica il microdominio congelato della v0.1-D:

1. colture cellulari su piastra;
2. una domanda e un target inferenziale;
3. esattamente un fattore, due livelli distinti e un endpoint primario;
4. `allocation_level`, `application_level`, `independently_assigned` tri-state e meccanismo
   operativo obbligatorio quando l'indipendenza è `TRUE`;
5. SampleSheet con colonne Appendix O e ID univoci; una cella nullable vuota significa
   `null`, mentre le stringhe segnaposto `NULL`/`unknown` sono vietate; `day_id`,
   `operator_id` e `incubator_id` possono rendere osservabile il confondimento per riga
   e devono usare soltanto ID pseudonimi;
6. tipo del fattore, unita biologica target ed estimand minimo espliciti;
7. verifica degli invarianti, tutti i sette `DeterminabilityState`, conteggi lifecycle scope-aware,
   Evidence View e anteprima della proof trace `GEN-001@1.0.0`;
8. compilazione canonica tramite `POST /v1/prospective/d0/compile`, ruleset fissato a
   `ntruth-core@0.2.0` e hard verifier server-side.

Prima della compilazione, lo stato live e la proof trace visibile sono controlli client non
autorevoli. Il click **Compila con verificatore D0** invia il draft e le righe al motore Python e
mostra separatamente stato canonico, capability, hard-verifier, checksum del ruleset e readiness.
Nessuno dei due percorsi crea annotazioni gold o certifica validita scientifica. I conteggi non
ancora riconciliati sono `NOT_REPORTED`, mai zero implicito; `effective_n` rimane separato da
`independent_n`. Se una riga è `excluded`, `exclusion_reason` deve riportare fase e autore, per
esempio `post-treatment | autore: AB | criterio: contaminazione`.

Il contratto API accetta al massimo 10.000 righe, 8 MiB di body complessivo e 64 campi extra per
riga. La sessione restituita e effimera nella memoria del processo; il riavvio dell'API la elimina.

Il canvas grafico libero è classificato **esteso sperimentale · post-v0.1-D**. È disattivo per
default e richiede un opt-in esplicito; il percorso D0 ufficiale usa wizard, tabelle, Core Profile
e proof trace.

## Test e build

```bash
pnpm test
pnpm build
```

`pnpm test` esegue Vitest/jsdom. `pnpm build` esegue il type-check TypeScript (`tsc -b`) e genera
gli asset Vite in `dist/`, inclusi poi nel wheel. Non è configurato uno script lint separato: il
type-check del build è il controllo statico frontend disponibile.

Per una verifica manuale minima:

1. aprire `/app/` e confermare che **Progettazione D0** sia attiva;
2. visitare i quattro passi, modificare un campo e controllare il riepilogo live;
3. aprire **Verifica**, compilare con la API e controllare capability, hard verifier, checksum e
   stato canonico; seguire poi una premessa fino all'Evidence View;
4. controllare che le fasi non osservate siano `NOT_REPORTED`;
5. raggiungere **Grafo** e verificare che il canvas resti nascosto finché non si abilita il gate
   sperimentale.

## Limiti della superficie desktop

- I dati iniziali sono sintetici e non costituiscono un risultato scientifico.
- Senza l'API locale la compilazione fallisce in modo visibile e resta disponibile soltanto la
  preview client non autorevole; non esiste fallback silenzioso a un verdetto locale.
- I dettagli tabellari della proof trace nella UI sono ancora una rappresentazione client; stato,
  capability, verifier e readiness canonici provengono dalla risposta API.
- Un wrapper Tauri firmato/notarizzato resta un deliverable separato: build web, firma,
  notarizzazione e release macOS sono evidenze distinte.
