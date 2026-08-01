"""N-Truth: ricostruzione verificabile di unita sperimentali e n indipendente.

Il core e deterministico e offline. Gli output sono inferenze automatiche
soggette a errore: non sostituiscono un biostatistico o un esperto di dominio
(PRD 21.4).
"""

__version__ = "0.1.0"

# Versioni dei contratti, riportate in ogni report (PRD FR-034).
SCHEMA_VERSION = "0.2.0"
PARSER_VERSION = "0.2.0"
GRAPH_VERSION = "0.2.0"
ONTOLOGY_VERSION = "0.1.0"

DISCLAIMER = (
    "N-Truth e uno strumento di supporto alla ricostruzione del disegno sperimentale. "
    "Gli output sono inferenze automatiche soggette a errore e non sostituiscono un "
    "biostatistico o un esperto di dominio. Il sistema non certifica validita, "
    "riproducibilita, conformita normativa o integrita della ricerca."
)
