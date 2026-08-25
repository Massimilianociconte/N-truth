"""Benchmark manifest for a future MVT-A run (PRD v7 §4.2).

Manifest only: no training execution, no corpus download.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum


class BenchmarkSplitPolicy(FrozenModel):
    """Isolation policy: train/dev/test must remain separate."""

    train_ids: tuple[str, ...] = ()
    dev_ids: tuple[str, ...] = ()
    test_ids: tuple[str, ...] = ()
    held_out_challenge_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_leakage(self) -> Self:
        pools = (
            ("train", set(self.train_ids)),
            ("dev", set(self.dev_ids)),
            ("test", set(self.test_ids)),
            ("held_out", set(self.held_out_challenge_ids)),
        )
        for i, (name_a, set_a) in enumerate(pools):
            for name_b, set_b in pools[i + 1 :]:
                overlap = set_a & set_b
                if overlap:
                    raise ValueError(
                        f"split leakage between {name_a} and {name_b}: {sorted(overlap)[:5]}"
                    )
        return self


class BenchmarkManifest(FrozenModel):
    """Machine-readable plan for MVT-A evaluation; not a result claim."""

    manifest_id: str
    schema_version: str = "7.0.0"
    domain_profile: str = "simple_cell_culture"
    task_stages: tuple[str, ...] = (
        "entity_candidate",
        "factor_candidate",
        "count_candidate",
        "evidence_candidate",
    )
    splits: BenchmarkSplitPolicy = Field(default_factory=BenchmarkSplitPolicy)
    real_anchor_required: bool = True
    synthetic_allowed_for_stress_only: bool = True
    external_eval_real_only: bool = True
    model_challengers: tuple[str, ...] = ()  # ids only; unqualified
    notes: str = "HOLD_PENDING_REAL_ANCHOR"

    def checksum(self) -> str:
        return content_checksum(self.model_dump(mode="json"))
