"""Stack di validazione a strati: la sintassi non equivale alla ricostruzione.

Grammar-constrained decoding e JSON valido attestano solo forma. Un report
scientificamente accettabile richiede schema, integrita referenziale, hard
verifier e conferma umana dei campi decisivi quando la policy lo impone.

Il semantic verifier e opzionale sul percorso D0 deterministico: puo restare
``NOT_RUN`` senza impedire ``scientifically_acceptable``. JSON/syntax valid
da soli non possono mai rendere ``scientifically_acceptable=True``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from ntruth.schemas.core import EvidenceType, FrozenModel

# Codici stabili per il layer evidence_support (non promuovere AUTHOR_ASSERTION sola).
AUTHOR_ASSERTION_ALONE_CODE = "author_assertion_alone_insufficient"
EVIDENCE_SUPPORT_EMPTY_CODE = "evidence_support_empty"
EVIDENCE_SUPPORT_PASS_CODE = "evidence_support_ok"


class ValidationLayer(StrEnum):
    """Livelli ordinati dello stack; grammar/JSON restano solo sintassi."""

    GRAMMAR_CONSTRAINED = "grammar_constrained"  # syntax only
    JSON_SCHEMA = "json_schema"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    TYPE_COMPATIBILITY = "type_compatibility"
    GRAPH_INVARIANTS = "graph_invariants"
    TEMPORAL_CONSISTENCY = "temporal_consistency"
    NUMERIC_CONSISTENCY = "numeric_consistency"
    EVIDENCE_SUPPORT = "evidence_support"
    CONTRADICTION_DETECTION = "contradiction_detection"
    HARD_VERIFIER = "hard_verifier"
    SEMANTIC_VERIFIER = "semantic_verifier"
    HUMAN_CONFIRMATION = "human_confirmation"


class LayerOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"
    NOT_APPLICABLE = "not_applicable"


class LayerResult(FrozenModel):
    layer: ValidationLayer
    outcome: LayerOutcome
    codes: tuple[str, ...] = ()
    message: str = ""


class ValidationStackReport(FrozenModel):
    """Never treat JSON-valid as scientific reconstruction.

    ``syntax_valid`` copre grammar/JSON. ``scientifically_acceptable`` e
    fail-closed e non puo essere True se mancano schema, referential integrity
    o hard verifier. Con policy che richiede conferma umana dei campi decisivi,
    serve anche ``human_confirmed_decisive``.
    """

    syntax_valid: bool  # grammar/json only
    schema_valid: bool
    referentially_valid: bool
    hard_verified: bool
    semantically_reviewed: bool  # only True if semantic verifier ran and passed
    human_confirmed_decisive: bool
    layers: tuple[LayerResult, ...]
    scientifically_acceptable: bool  # derived, fail-closed
    require_human_confirmation: bool = True

    @model_validator(mode="after")
    def _scientifically_acceptable_is_fail_closed(self) -> Self:
        """scientifically_acceptable requires schema, referential, hard, and
        human_confirmed_decisive when required_by_policy (require_human_confirmation).
        """

        gates = (
            self.schema_valid
            and self.referentially_valid
            and self.hard_verified
            and (self.human_confirmed_decisive if self.require_human_confirmation else True)
        )
        # Syntax alone must never certify reconstruction.
        if self.scientifically_acceptable and not gates:
            raise ValueError(
                "scientifically_acceptable richiede schema_valid, "
                "referentially_valid, hard_verified"
                + (
                    " e human_confirmed_decisive"
                    if self.require_human_confirmation
                    else ""
                )
                + "; JSON/syntax valid non bastano"
            )
        if self.scientifically_acceptable and not self.schema_valid:
            raise ValueError(
                "scientifically_acceptable non puo essere True con solo syntax_valid"
            )
        if self.semantically_reviewed:
            semantic = _layer_map(self.layers).get(ValidationLayer.SEMANTIC_VERIFIER)
            if semantic is None or semantic.outcome is not LayerOutcome.PASS:
                raise ValueError(
                    "semantically_reviewed=True richiede semantic_verifier con outcome=pass"
                )
        return self


def evidence_support_from_types(
    decisive_types: Iterable[EvidenceType | str],
) -> LayerResult:
    """Esito del layer evidence_support dai tipi di evidenza decisivi.

    AUTHOR_ASSERTION da sola non soddisfa il layer: non puo chiudere la
    determinabilita ne sostituire fatti strutturali o conferma umana.
    """

    normalized: list[EvidenceType] = []
    for item in decisive_types:
        if isinstance(item, EvidenceType):
            normalized.append(item)
        else:
            normalized.append(EvidenceType(str(item)))
    unique = frozenset(normalized)
    if not unique:
        return LayerResult(
            layer=ValidationLayer.EVIDENCE_SUPPORT,
            outcome=LayerOutcome.FAIL,
            codes=(EVIDENCE_SUPPORT_EMPTY_CODE,),
            message="nessun tipo di evidenza decisivo fornito",
        )
    if unique == {EvidenceType.AUTHOR_ASSERTION}:
        return LayerResult(
            layer=ValidationLayer.EVIDENCE_SUPPORT,
            outcome=LayerOutcome.FAIL,
            codes=(AUTHOR_ASSERTION_ALONE_CODE,),
            message=(
                "AUTHOR_ASSERTION da sola non soddisfa evidence_support: "
                "non chiude la determinabilita ne certifica la ricostruzione"
            ),
        )
    return LayerResult(
        layer=ValidationLayer.EVIDENCE_SUPPORT,
        outcome=LayerOutcome.PASS,
        codes=(EVIDENCE_SUPPORT_PASS_CODE,),
        message="evidenze decisive oltre la sola AUTHOR_ASSERTION",
    )


def build_validation_stack_report(
    *,
    schema_valid: bool,
    hard_verifier_passed: bool,
    referentially_valid: bool | None = None,
    grammar_constrained_ok: bool | None = None,
    json_schema_ok: bool | None = None,
    type_compatibility_ok: bool | None = None,
    graph_invariants_ok: bool | None = None,
    temporal_consistency_ok: bool | None = None,
    numeric_consistency_ok: bool | None = None,
    evidence_support: LayerResult | None = None,
    contradiction_free: bool | None = None,
    semantic_invoked: bool = False,
    semantic_passed: bool = False,
    human_confirmed_decisive: bool = False,
    require_human_confirmation: bool = True,
    failed_codes: Mapping[ValidationLayer | str, Sequence[str]] | None = None,
    layer_messages: Mapping[ValidationLayer | str, str] | None = None,
) -> ValidationStackReport:
    """Costruisce un report a strati da segnali gia disponibili.

    Policy D0 deterministico:
    - ``scientifically_acceptable`` = schema ∧ referential ∧ hard ∧
      (human se ``require_human_confirmation``);
    - ``semantic_verifier`` puo restare ``NOT_RUN`` senza bloccare
      l'accettabilita scientifica sul path D0;
    - grammar/JSON ok non bastano mai: ``scientifically_acceptable`` non
      diventa True con solo ``syntax_valid``.
    """

    codes = _normalize_failed_codes(failed_codes)
    messages = _normalize_messages(layer_messages)

    # JSON Schema layer: prefer explicit signal, else fall back to schema_valid.
    json_ok = schema_valid if json_schema_ok is None else json_schema_ok
    # Grammar is syntax-only; if unknown, treat as not_run rather than inventing pass.
    grammar_outcome = _bool_or_not_run(
        grammar_constrained_ok, ValidationLayer.GRAMMAR_CONSTRAINED
    )
    # Without an explicit grammar signal, syntax is JSON-valid only.
    syntax_valid = bool(json_ok) and (
        grammar_constrained_ok is True or grammar_constrained_ok is None
    )
    if grammar_constrained_ok is False:
        syntax_valid = False

    ref_valid = schema_valid if referentially_valid is None else referentially_valid
    hard_ok = hard_verifier_passed

    semantic_outcome = LayerOutcome.NOT_RUN
    if semantic_invoked:
        semantic_outcome = LayerOutcome.PASS if semantic_passed else LayerOutcome.FAIL
    semantically_reviewed = semantic_outcome is LayerOutcome.PASS

    if evidence_support is None:
        evidence_layer = LayerResult(
            layer=ValidationLayer.EVIDENCE_SUPPORT,
            outcome=LayerOutcome.NOT_RUN,
            codes=tuple(codes.get(ValidationLayer.EVIDENCE_SUPPORT, ())),
            message=messages.get(ValidationLayer.EVIDENCE_SUPPORT, ""),
        )
    else:
        if evidence_support.layer is not ValidationLayer.EVIDENCE_SUPPORT:
            raise ValueError("evidence_support deve usare ValidationLayer.EVIDENCE_SUPPORT")
        evidence_layer = evidence_support

    # Explicit fail when required and not confirmed; N/A when policy waives.
    if require_human_confirmation:
        human_outcome = (
            LayerOutcome.PASS if human_confirmed_decisive else LayerOutcome.FAIL
        )
    else:
        human_outcome = (
            LayerOutcome.PASS
            if human_confirmed_decisive
            else LayerOutcome.NOT_APPLICABLE
        )

    layers: list[LayerResult] = [
        _result(
            ValidationLayer.GRAMMAR_CONSTRAINED,
            grammar_outcome,
            codes,
            messages,
            default_pass_message="grammar-constrained decoding ok (solo sintassi)",
            default_fail_message="grammar-constrained decoding fallito",
            default_not_run_message="grammar-constrained non eseguito o non disponibile",
        ),
        _result(
            ValidationLayer.JSON_SCHEMA,
            LayerOutcome.PASS if json_ok else LayerOutcome.FAIL,
            codes,
            messages,
            default_pass_message="JSON/schema di forma valido (solo sintassi/struttura)",
            default_fail_message="JSON Schema non valido",
        ),
        _result(
            ValidationLayer.REFERENTIAL_INTEGRITY,
            LayerOutcome.PASS if ref_valid else LayerOutcome.FAIL,
            codes,
            messages,
            default_pass_message="integrita referenziale ok",
            default_fail_message="integrita referenziale fallita",
        ),
        _optional_bool_layer(
            ValidationLayer.TYPE_COMPATIBILITY,
            type_compatibility_ok,
            codes,
            messages,
            pass_message="compatibilita dei tipi ok",
            fail_message="compatibilita dei tipi fallita",
        ),
        _optional_bool_layer(
            ValidationLayer.GRAPH_INVARIANTS,
            graph_invariants_ok,
            codes,
            messages,
            pass_message="invarianti del grafo ok",
            fail_message="invarianti del grafo falliti",
        ),
        _optional_bool_layer(
            ValidationLayer.TEMPORAL_CONSISTENCY,
            temporal_consistency_ok,
            codes,
            messages,
            pass_message="coerenza temporale ok",
            fail_message="coerenza temporale fallita",
        ),
        _optional_bool_layer(
            ValidationLayer.NUMERIC_CONSISTENCY,
            numeric_consistency_ok,
            codes,
            messages,
            pass_message="coerenza numerica ok",
            fail_message="coerenza numerica fallita",
        ),
        evidence_layer,
        _optional_bool_layer(
            ValidationLayer.CONTRADICTION_DETECTION,
            contradiction_free,
            codes,
            messages,
            pass_message="nessuna contraddizione rilevata",
            fail_message="contraddizioni rilevate",
        ),
        _result(
            ValidationLayer.HARD_VERIFIER,
            LayerOutcome.PASS if hard_ok else LayerOutcome.FAIL,
            codes,
            messages,
            default_pass_message="hard verifier complete senza violazioni",
            default_fail_message="hard verifier fallito o con violazioni",
        ),
        _result(
            ValidationLayer.SEMANTIC_VERIFIER,
            semantic_outcome,
            codes,
            messages,
            default_pass_message="semantic verifier eseguito e superato",
            default_fail_message="semantic verifier eseguito e fallito",
            default_not_run_message=(
                "semantic verifier non eseguito (opzionale sul path D0 deterministico)"
            ),
        ),
        _result(
            ValidationLayer.HUMAN_CONFIRMATION,
            human_outcome,
            codes,
            messages,
            default_pass_message="campi decisivi confermati da umano",
            default_fail_message="manca conferma umana dei campi decisivi",
            default_not_applicable_message="conferma umana non richiesta dalla policy",
        ),
    ]

    scientifically_acceptable = bool(
        schema_valid
        and ref_valid
        and hard_ok
        and (human_confirmed_decisive if require_human_confirmation else True)
    )

    return ValidationStackReport(
        syntax_valid=syntax_valid,
        schema_valid=schema_valid,
        referentially_valid=ref_valid,
        hard_verified=hard_ok,
        semantically_reviewed=semantically_reviewed,
        human_confirmed_decisive=human_confirmed_decisive,
        layers=tuple(layers),
        scientifically_acceptable=scientifically_acceptable,
        require_human_confirmation=require_human_confirmation,
    )


def _layer_map(layers: Sequence[LayerResult]) -> dict[ValidationLayer, LayerResult]:
    return {item.layer: item for item in layers}


def _normalize_failed_codes(
    failed_codes: Mapping[ValidationLayer | str, Sequence[str]] | None,
) -> dict[ValidationLayer, tuple[str, ...]]:
    if not failed_codes:
        return {}
    out: dict[ValidationLayer, tuple[str, ...]] = {}
    for key, values in failed_codes.items():
        layer = key if isinstance(key, ValidationLayer) else ValidationLayer(str(key))
        out[layer] = tuple(str(code) for code in values)
    return out


def _normalize_messages(
    layer_messages: Mapping[ValidationLayer | str, str] | None,
) -> dict[ValidationLayer, str]:
    if not layer_messages:
        return {}
    out: dict[ValidationLayer, str] = {}
    for key, value in layer_messages.items():
        layer = key if isinstance(key, ValidationLayer) else ValidationLayer(str(key))
        out[layer] = str(value)
    return out


def _bool_or_not_run(value: bool | None, _layer: ValidationLayer) -> LayerOutcome:
    if value is None:
        return LayerOutcome.NOT_RUN
    return LayerOutcome.PASS if value else LayerOutcome.FAIL


def _optional_bool_layer(
    layer: ValidationLayer,
    value: bool | None,
    codes: Mapping[ValidationLayer, tuple[str, ...]],
    messages: Mapping[ValidationLayer, str],
    *,
    pass_message: str,
    fail_message: str,
) -> LayerResult:
    if value is None:
        outcome = LayerOutcome.NOT_RUN
        default_message = f"{layer.value} non eseguito"
    elif value:
        outcome = LayerOutcome.PASS
        default_message = pass_message
    else:
        outcome = LayerOutcome.FAIL
        default_message = fail_message
    return _result(
        layer,
        outcome,
        codes,
        messages,
        default_pass_message=pass_message,
        default_fail_message=fail_message,
        default_not_run_message=default_message,
    )


def _result(
    layer: ValidationLayer,
    outcome: LayerOutcome,
    codes: Mapping[ValidationLayer, tuple[str, ...]],
    messages: Mapping[ValidationLayer, str],
    *,
    default_pass_message: str = "",
    default_fail_message: str = "",
    default_not_run_message: str = "",
    default_not_applicable_message: str = "",
) -> LayerResult:
    layer_codes = tuple(codes.get(layer, ()))
    if outcome is LayerOutcome.FAIL and not layer_codes:
        layer_codes = (f"{layer.value}_failed",)
    if layer in messages:
        message = messages[layer]
    elif outcome is LayerOutcome.PASS:
        message = default_pass_message
    elif outcome is LayerOutcome.FAIL:
        message = default_fail_message
    elif outcome is LayerOutcome.NOT_APPLICABLE:
        message = default_not_applicable_message
    else:
        message = default_not_run_message
    return LayerResult(
        layer=layer,
        outcome=outcome,
        codes=layer_codes if outcome is LayerOutcome.FAIL else (),
        message=message,
    )


__all__ = [
    "AUTHOR_ASSERTION_ALONE_CODE",
    "EVIDENCE_SUPPORT_EMPTY_CODE",
    "EVIDENCE_SUPPORT_PASS_CODE",
    "LayerOutcome",
    "LayerResult",
    "ValidationLayer",
    "ValidationStackReport",
    "build_validation_stack_report",
    "evidence_support_from_types",
]
