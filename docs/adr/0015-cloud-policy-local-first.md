# ADR-0015 — Cloud policy: local-first hard

**Status:** accepted
**Date:** 2026-08-25
**Scope:** PRD v9 §26.9 (cloud), NFR-01, docs/resource-funding-gate.md

## Context

NFR-01 richiede local-first senza cloud silenzioso. Il deterministico core non ha
alcun requisito di rete e il server locale è loopback-only; la lane ML opzionale
non è autorizzata a scaricare modelli come parte del setup normale. Esistono
però scenari reali — valutazioni su larga scala, hosting di modelli, storage
remoto condiviso con collaboratori — in cui un dipartimento o un progetto
finanziato potrebbe voler usare servizi cloud. Senza una policy scritta, il
rischio è l'egresso silenzioso di documenti, dataset o metadati scientifici, che
distruggerebbe la proprietà di local-first e la provenienza.

## Decision

1. **Local-first hard.** Il default operativo è interamente offline: nessuna
   telemetria, nessun download automatico, nessuna chiamata di rete dal core.
   Ogni capability di rete è disabilitata by default e fail-closed.
2. **Cloud ammesso solo funded/university.** Un uso cloud è consentito soltanto
   se esiste un progetto istituzionalmente finanziato o un accordo universitario
   che lo copra, con:
   - permission scope esplicito ed enumerato (quali documenti/dataset/modelli/
     metadati possono lasciare il dispositivo, verso quale servizio, per quale
     finalità);
   - consenso utente esperto per scope item, mai bucket generici;
   - un `DataUseGrant`/`DataUseRecord` che vincola l'uso e resta auditable
     (PRD v9 §27.2, NFR-46);
   - indicazione visibile e permanente nell'UI/CLI quando qualsiasi flusso verso
     l'esterno è attivo.
3. **Mai silent.** In assenza di grant valido, ogni tentativo di egress fallisce
   in modo visibile. Nessuna code path può attivare rete come effetto collaterale
   di un'altra operazione (es. apertura documento, aggiornamento, telemetria di
   crash).
4. Il codice che introduce una surface di rete deve dichiararla in un test che
   ne dimostri lo stato default-off.

## Consequences

- Zero raccolta di metriche d'uso: le decisioni di prodotto si basano su pilot
  espliciti, non su telemetria.
- Le collaborazioni cloud richiedono lavoro amministrativo upfront (grant,
  scope, attestazioni); è un costo accettato.
- Funzionalità dipendenti da servizi remoti non possono entrare nel default
  shipped; restano estensioni governate da grant.

## Alternatives considered

- **Opt-in cloud generico con consenso una tantum:** rifiutato; un consenso
  aggregato non è permission scope esplicito e normalizza l'egresso.
- **Cloud "anonymous"/aggregato per telemetria:** rifiutato; anche dati
  aggregati sono egresso silenzioso e in contrasto con NFR-01/NFR-02.
- **Divieto assoluto permanente, incluso istituzionale:** rifiutato; chiude
  collaborazioni finanziate legittime. La policy li ammette lungo il percorso
  grant-based, senza eccezioni implicite.

## Review trigger

Revisione obbligatoria se emerge qualsiasi percorso di egresso non coperto, o
prima della prima attivazione reale di un progetto funded/university; nuovo ADR
sostitutivo per cambi di policy.
