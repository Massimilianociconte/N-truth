"""Estrazione dei termini del modello (effetti casuali/cluster).

Due direzioni di errore contano: un termine perso produce un falso allarme
("il modello non rappresenta la dipendenza"), un termine inventato sopprime un
alert di pseudoreplicazione reale. Frasi di disegno e menzioni negate non
devono mai diventare termini del modello.
"""

from __future__ import annotations

import pytest

from ntruth.extract.text_extract import _model_accounts_for
from ntruth.schemas.graph import NodeType

A, C, D = NodeType.ANIMAL, NodeType.CELL_CULTURE, NodeType.HUMAN_DONOR


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A linear mixed model with a random intercept for mouse was fitted", (A,)),
        ("Animal was included as a random effect in a linear mixed model", (A,)),
        ("a mixed model with animal and litter as random effects", (A, NodeType.LITTER)),
        ("GLMM with random effects of litter and cage", (NodeType.LITTER, NodeType.CAGE)),
        ("LMM: response ~ treatment + (1|animal_id)", (A,)),
        ("LMM: response ~ treatment + (1 | Mouse/Cell)", (A, NodeType.CELL)),
        ("LMM: y ~ treatment + (1 + time | subject)", (D,)),
        ("mixed model: y ~ drug + (1|cage) + (1|cage:animal)", (NodeType.CAGE, A)),
        ("mixed model with random = ~1|animal", (A,)),
        ("random intercepts per culture", (C,)),
        ("clustered standard errors by animal were used", (A,)),
    ],
)
def test_declared_model_terms_are_recovered(text: str, expected: tuple[NodeType, ...]) -> None:
    assert _model_accounts_for(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # Frasi di disegno, non termini del modello.
        "linear mixed model with treatment as fixed effect; 30 cells per animal were analysed",
        "mixed-effects model; cells nested within cultures were treated as independent",
        "hierarchical model fitted for each donor separately",
        "Mice were analysed per cage. A mixed model was used.",
        "cells were clustered by Louvain and a mixed model was used",
        # Menzioni negate.
        "without random effects for animal, a mixed model was fitted",
        "a random effect of animal was not included",
        "animal was not modelled as a random effect",
        "a linear mixed model rather than a random intercept for animal",
        # Termini non strutturali o ambigui.
        "random effect for treatment",
        "random effects for experiment",
    ],
)
def test_design_phrases_and_negations_are_not_model_terms(text: str) -> None:
    assert _model_accounts_for(text) == ()
