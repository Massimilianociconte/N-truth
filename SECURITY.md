# Security policy

N-Truth analizza documenti scientifici locali e deve considerarli sempre input non fidato.

## Versioni supportate

Solo la revisione corrente del ramo di sviluppo riceve correzioni di sicurezza. Non esiste ancora
una release scientifica stabile.

## Segnalazioni

Non allegare documenti riservati, dati personali, credenziali o sample ID reali a una segnalazione
pubblica. Descrivere il problema con una fixture sintetica minima. Per una disclosure privata usare
[GitHub Private Vulnerability Reporting](https://github.com/Massimilianociconte/N-truth/security/advisories/new).
Se il canale non è disponibile, aprire una issue pubblica priva di dettagli tecnici o dati sensibili
chiedendo al maintainer un contatto privato.

## Confini di fiducia

- Il core non apre connessioni di rete e non carica file automaticamente.
- L'API è single-user, senza autenticazione e accetta percorsi locali. Deve restare vincolata a
  `127.0.0.1`; non esporla su `0.0.0.0`, LAN/Internet o tramite reverse proxy. `TrustedHostMiddleware`
  limita gli host HTTP ma non sostituisce isolamento di rete e autenticazione.
- DOCX/XLSX sono archivi non fidati; macro, traversal e decompressione anomala sono bloccati.
- Formule di foglio e prompt injection sono dati da neutralizzare/segnalare, mai istruzioni.
- Gli script R, Python e R Markdown vengono importati come testo read-only con policy
  `never_execute`: N-Truth non deve eseguirli durante parsing, analisi o anteprima.
- Il codice statistico può dichiarare un clustering candidato, ma non può determinare
  automaticamente il livello di allocazione.
- I candidate fact di un futuro parser AI sono input non fidato: schema, riferimenti,
  coordinate ed evidence span devono essere validati prima di entrare nel grafo.
- Un report non certifica validita scientifica, privacy o conformita normativa.

## Dati, export e privacy

- L'analisi locale non concede automaticamente il diritto di annotare, addestrare,
  condividere o redistribuire un asset.
- I gate di governance sono fail-closed: record assente, checksum non coerente,
  autorizzazione revocata/scaduta o uso non elencato devono produrre un diniego esplicito.
- Lo scanner privacy locale produce finding stand-off con coordinate, preview mascherata e
  hash. È assistivo e non sostituisce una verifica privacy o una DPIA.
- Una copia redatta è una derivata separata; la fonte non deve essere mutata in-place.
- Il flusso applicativo standard produce `privacy-scan.json` e `share-readiness.json` con
  distribuzione negata per default. Endpoint e CLI di readiness invocano i gate fail-closed,
  ma non effettuano trasferimenti.
- Una chiamata di libreria che scrive soltanto un `Report` senza `DocumentIR` non può produrre
  la scansione delle fonti e non va descritta come autorizzazione alla distribuzione.

Una vulnerabilita e chiusa solo con riproduzione, patch, test di regressione e verifica del confine
locale/offline interessato.
