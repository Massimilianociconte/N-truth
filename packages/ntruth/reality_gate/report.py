"""Report del Reality Gate: esito machine-readable e blocker report umano."""

from __future__ import annotations

from ntruth.reality_gate.gate import RealityGateResult
from ntruth.schemas.core import content_checksum


def machine_readable_result(result: RealityGateResult) -> dict[str, object]:
    """JSON stabile per CI e registri (nessun claim implicito)."""
    payload = result.model_dump(mode="json")
    payload["checksum"] = content_checksum(result.model_dump(mode="json"))
    return payload


def human_blocker_report(result: RealityGateResult) -> str:
    """Report leggibile dei blocker, dimensione per dimensione."""
    lines = [
        "Reality Gate report (PRD v7 §0.7) - fail-closed",
        f"  engineering_readiness: {result.engineering_readiness.status}",
        f"  data_readiness: {result.data_readiness.status}",
        f"  scientific_validation: {result.scientific_validation.status}",
        f"  substantive_training_allowed: {result.substantive_training_allowed}",
        f"  ai_claims_allowed: {result.ai_claims_allowed}",
    ]
    if result.overall_blockers:
        lines.append("Blockers:")
        lines.extend(f"  - {blocker}" for blocker in result.overall_blockers)
    else:
        lines.append("No registered blockers.")
    return "\n".join(lines)
