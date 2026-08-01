# Privacy and DPIA screening

**Stato:** questionario preliminare. Se una risposta evidenzia dati personali o categorie
particolari, interrompere l'intake e coinvolgere DPO/ufficio privacy.

1. I file contengono nomi, email, path utente, firme, metadati autore o identificativi diretti?
2. Gli ID campione possono essere collegati a persone tramite una tabella separata?
3. Sono presenti dati sanitari, genetici, biometrici o altre categorie particolari?
4. Lo scopo puo essere raggiunto con dati anonimi/sintetici o rimuovendo colonne?
5. Chi determina finalita e mezzi, chi tratta i dati e chi puo accedervi?
6. Quali base giuridica, retention, cancellazione e gestione revoca sono documentate?
7. Esistono trasferimenti, backup o servizi cloud? Il default N-Truth deve restare offline.
8. Il trattamento introduce monitoraggio, ranking personale o decisioni automatizzate?
9. Sono documentati rischio, probabilita, impatto e misure tecniche/organizzative?
10. Il DPO ha stabilito se serve una DPIA formale?

Lo scanner locale può segnalare email, path, nomi esplicitamente etichettati e ID
campione/persona tramite finding stand-off. Falsi positivi e falsi negativi sono possibili:
il risultato richiede revisione umana e non è una qualificazione giuridica.

N-Truth non anonimizza automaticamente i dati e non può dichiarare conformità GDPR. La
redazione produce una copia derivata e non modifica la fonte; l'uso di una policy
`acknowledged` richiede una decisione umana documentata.
