"""Trasparenza sul dominio e preflight conservativo (PRD NFR-14).

Questa baseline non possiede ancora una validazione scientifica indipendente o un
detector OOD calibrato. Il software deve dirlo prima dell'uso, senza trasformare la
presenza di regole di dominio in una dichiarazione di validazione.
"""

from __future__ import annotations

from ntruth.schemas.report import DomainTransparency, DomainValidationStatus

# Domini rappresentati dal ruleset/schema corrente. "Supportato" significa soltanto
# che il software sa rappresentarne i concetti, non che le prestazioni siano validate.
SUPPORTED_DOMAINS: tuple[str, ...] = (
    "animal",
    "cell_culture",
    "quantitative_microscopy",
    "single_cell",
)

# Va popolato esclusivamente dopo external validation e sign-off indipendente.
VALIDATED_DOMAINS: tuple[str, ...] = ()


def assess_domain(domain: str | None) -> DomainTransparency:
    """Restituisce lo stato dichiarato senza fingere una valutazione OOD appresa."""

    normalized = (domain or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return DomainTransparency(
            declared_domain="unknown",
            validation_status=DomainValidationStatus.UNKNOWN,
            supported_domains=SUPPORTED_DOMAINS,
            validated_domains=VALIDATED_DOMAINS,
            warning=(
                "Dominio non dichiarato: N-Truth non puo stabilire se l'uso rientra nel "
                "perimetro rappresentato e non dispone di una valutazione OOD calibrata."
            ),
        )

    if normalized in VALIDATED_DOMAINS:
        return DomainTransparency(
            declared_domain=normalized,
            validation_status=DomainValidationStatus.VALIDATED,
            supported_domains=SUPPORTED_DOMAINS,
            validated_domains=VALIDATED_DOMAINS,
            warning="",
            requires_acknowledgement=False,
        )

    if normalized in SUPPORTED_DOMAINS:
        return DomainTransparency(
            declared_domain=normalized,
            validation_status=DomainValidationStatus.UNVALIDATED,
            supported_domains=SUPPORTED_DOMAINS,
            validated_domains=VALIDATED_DOMAINS,
            warning=(
                f"Il dominio '{normalized}' e rappresentato dal ruleset ma non e ancora "
                "validato scientificamente su un external set indipendente. OOD non valutato."
            ),
        )

    return DomainTransparency(
        declared_domain=normalized,
        validation_status=DomainValidationStatus.OUT_OF_SCOPE,
        supported_domains=SUPPORTED_DOMAINS,
        validated_domains=VALIDATED_DOMAINS,
        warning=(
            f"Il dominio '{normalized}' e fuori dal perimetro rappresentato dalla baseline. "
            "Non usare l'output come inferenza scientificamente validata. OOD non valutato."
        ),
    )
