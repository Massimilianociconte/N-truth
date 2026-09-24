# Annotations

## Reality check P0 (fase attiva)

Vedi [`reality-check/README.md`](reality-check/README.md):

- guideline: `docs/annotation-reality-check-p0-v0.1.md`
- schema Real Experiment Bundle
- pilot interno 3–5 (**non gold**)
- formal 10–20 (vuoto finché freeze)

`training_eligible` e `gold` restano **false** in questa fase.

## Candidate annotations (UI)

Le correzioni utente esportate dalla UI/API sono candidate annotations separate. Non sono gold e
non entrano nel training finché un workflow di curation non le promuove con reviewer e versione
della guideline, double annotation/adjudication quando richiesta e record di governance con uso
`train`. Una conferma UI non equivale ad expert answer e una correzione verificata non amplia la
licenza della fonte. Le directory di lavoro locali restano ignorate da Git.
