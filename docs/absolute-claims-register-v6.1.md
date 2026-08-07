# Registro delle affermazioni assolute - revisione v6.1

L'audit ha fornito cinque formulazioni da rimuovere o correggere. La verifica sul PDF
v6.0 distingue la presenza letterale dal rischio interpretativo: una frase assente non
viene falsamente descritta come cancellata, ma la v6.1 introduce comunque la formula
normativa corretta.

| Formulazione auditata | Presenza nella v6.0 | Decisione v6.1 | Formula normativa |
|---|---|---|---|
| "Il prospective design azzera l'ambiguità" | Non trovata letteralmente. La v6.0 afferma che il corpus prospettico è "meno ambiguo". | Chiarimento preventivo. | "Il prospective design riduce drasticamente l'ambiguità e rende osservabili le deviazioni tra piano ed esecuzione; non elimina errori, deviazioni o reporting gap." |
| "Il motore deriva i gradi di libertà in modo riproducibile al 100%" | Non trovata. La v6.0 distingue già capacità e limiti statistici. | Divieto esplicito dell'equivalenza. | "Il motore applica deterministicamente il ruleset supportato; scelta del modello statistico e gradi di libertà restano distinti e richiedono assunzioni dichiarate." |
| "Gli encoder hanno rischio di allucinazione zero" | Non trovata. | Aggiunta di un limite tecnico. | "Gli encoder non generano testo libero, ma possono produrre errori di estrazione, classificazione, relazione e calibrazione." |
| "È necessario abbandonare un modello da 8B" | Non trovata. La v6.0 indicava una cascata come target preferito e 3-8B come ordine realistico. | Rimossi intervalli dimensionali dal requisito normativo; confronto obbligatorio. | "Le architetture monolitiche sono ammesse se rispettano il resource budget misurato e superano la cascata sulle metriche preregistrate." |
| Stime RAM precise come requisito universale | Presente come target `peak RAM <=20 GB` e in alcuni envelope ingegneristici. | Sostituzione con profili benchmark-derived. | "Budget, context, batch e cache sono accettati solo dopo benchmark versionato sull'hardware target; valori non misurati restano ipotesi." |

## Soglie rese provvisorie

Qualunque valore come `F1 > 0,80`, `IAA > 0,75` o `degradation <10%` è etichettato
`PROVISIONAL`. Dopo il pilot devono essere riportati intervalli bootstrap, prevalenza,
metrica esatta, human ceiling, costo degli errori critici, confronto con baseline e
riduzione del tempo di revisione. Le soglie definitive appartengono al protocollo di
valutazione approvato, non al PRD come costanti a priori.
