"""Manifest di progetto e di licenza (PRD 14.5, FR-001, FR-007, FR-032).

Governance conservativa: nessun asset entra nella pipeline senza fonte primaria,
licenza esplicita, snapshot, checksum, attribuzione e revisione (PRD 14).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from ntruth.schemas.core import NTruthModel, content_checksum

AUTOMATED_CORPUS_LICENSES = frozenset(
    {
        "CC0-1.0",
        "CC-BY-4.0",
        "HTTPS://CREATIVECOMMONS.ORG/PUBLICDOMAIN/ZERO/1.0",
        "HTTPS://CREATIVECOMMONS.ORG/LICENSES/BY/4.0",
    }
)

_USE_ALIASES = {
    "analyze": frozenset({"analyze", "analysis"}),
    "annotate": frozenset({"annotate", "annotation"}),
    "train": frozenset({"train", "training"}),
    "share": frozenset({"share", "sharing"}),
    "redistribute": frozenset({"redistribute", "redistribution"}),
}


class LicenseTier(StrEnum):
    """Tier di ammissione (PRD 14, Figura 3)."""

    A = "tier_a"  # licenza esplicita e compatibile
    B = "tier_b"  # condizionale: serve revisione scritta
    C = "tier_c"  # escluso: non entra nella pipeline
    UNKNOWN = "unknown"


class AssetStatus(StrEnum):
    APPROVED_TIER_A = "approved_tier_a"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class BundleFileRole(StrEnum):
    """Ruolo esplicito di una fonte dentro un Experiment Bundle (PRD 18.3)."""

    METHODS = "methods"
    EXPERIMENT_DESCRIPTION = "experiment_description"
    FIGURE_CAPTION = "figure_caption"
    GROUP_SCHEME = "group_scheme"
    SAMPLE_SHEET = "sample_sheet"
    FILE_TO_SAMPLE_MAPPING = "file_to_sample_mapping"
    STATISTICAL_CODE = "statistical_code"
    SUPPLEMENT = "supplement"
    EXPERT_ANSWER = "expert_answer"
    OTHER = "other"


class BundleFileReference(NTruthModel):
    """File e ruolo: l'associazione non viene mai dedotta dal basename."""

    file_id: str
    role: BundleFileRole
    label: str | None = None


class FileToSampleMapping(NTruthModel):
    """Relazione dichiarata tra un file dati e una chiave campione."""

    data_file_id: str
    sample_id: str
    sample_sheet_file_id: str | None = None


class ExperimentBundleManifest(NTruthModel):
    """Unita esplicita multi-file per un singolo esperimento (PRD FR-006)."""

    bundle_id: str
    title: str
    files: tuple[BundleFileReference, ...] = Field(min_length=1)
    file_to_sample: tuple[FileToSampleMapping, ...] = ()
    group_scheme: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    declared_facts: tuple[str, ...] = ()
    expert_declarations: tuple[str, ...] = ()
    governance_record_id: str | None = None
    governance_record_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provenance_note: str | None = None

    @model_validator(mode="after")
    def _validate_references(self) -> ExperimentBundleManifest:
        if (self.governance_record_id is None) != (self.governance_record_hash is None):
            raise ValueError(
                "governance_record_id e governance_record_hash vanno registrati insieme"
            )
        pairs = [(item.file_id, item.role) for item in self.files]
        if len(pairs) != len(set(pairs)):
            raise ValueError("riferimento file/ruolo duplicato nell'Experiment Bundle")
        file_ids = {item.file_id for item in self.files}
        sample_sheet_ids = {
            item.file_id for item in self.files if item.role is BundleFileRole.SAMPLE_SHEET
        }
        for mapping in self.file_to_sample:
            if mapping.data_file_id not in file_ids:
                raise ValueError(
                    f"file_to_sample riferisce file non assegnato: {mapping.data_file_id}"
                )
            if (
                mapping.sample_sheet_file_id is not None
                and mapping.sample_sheet_file_id not in sample_sheet_ids
            ):
                raise ValueError(
                    "sample_sheet_file_id deve riferire un file con ruolo sample_sheet"
                )
        return self

    def checksum(self) -> str:
        return content_checksum(self.model_dump(mode="json"))


class LicenseManifest(NTruthModel):
    """Record per singolo asset (PRD 14.5)."""

    asset_id: str
    asset_type: str
    source_url: str | None = None
    license_spdx_or_uri: str | None = None
    license_evidence_url: str | None = None
    retrieved_at: str | None = None
    sha256: str | None = None
    allowed_uses: tuple[str, ...] = ()
    commercial_compatibility_reviewed: bool = False
    attribution_text: str | None = None
    dataset_split: str | None = None
    reviewer: str | None = None
    tier: LicenseTier = LicenseTier.UNKNOWN
    status: AssetStatus = AssetStatus.PENDING_REVIEW

    @property
    def training_allowed(self) -> bool:
        """FR-032: training bloccato se il manifest e incompleto."""
        return self.permits("train", automated_release=True)

    @property
    def automated_corpus_license(self) -> bool:
        if not self.license_spdx_or_uri:
            return False
        normalized = self.license_spdx_or_uri.strip().rstrip("/").upper()
        return normalized in AUTOMATED_CORPUS_LICENSES

    def permits(self, use: str, *, automated_release: bool = False) -> bool:
        """Valuta un uso dichiarato senza trasformare assenza in permesso."""

        complete = all(
            [
                self.license_spdx_or_uri,
                self.license_evidence_url,
                self.sha256,
                self.retrieved_at,
                self.attribution_text,
            ]
        )
        normalized_use = use.strip().lower()
        aliases = _USE_ALIASES.get(normalized_use, frozenset({normalized_use}))
        explicitly_allowed = bool(aliases & {item.strip().lower() for item in self.allowed_uses})
        return bool(
            complete
            and self.tier is LicenseTier.A
            and self.status is AssetStatus.APPROVED_TIER_A
            and explicitly_allowed
            and (not automated_release or self.automated_corpus_license)
        )

    def manifest_hash(self) -> str:
        return content_checksum(self.model_dump(mode="json"))

    def blocking_gaps(self) -> list[str]:
        gaps: list[str] = []
        for field_name in (
            "license_spdx_or_uri",
            "license_evidence_url",
            "sha256",
            "retrieved_at",
            "attribution_text",
        ):
            if not getattr(self, field_name):
                gaps.append(field_name)
        if self.tier is not LicenseTier.A:
            gaps.append(f"tier={self.tier}")
        return gaps


class ProjectFile(NTruthModel):
    """File registrato nel progetto locale."""

    file_id: str
    filename: str
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str
    license_manifest: LicenseManifest | None = None
    governance_record_id: str | None = None
    governance_record_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _governance_reference_is_versioned(self) -> ProjectFile:
        if (self.governance_record_id is None) != (self.governance_record_hash is None):
            raise ValueError(
                "governance_record_id e governance_record_hash vanno registrati insieme"
            )
        return self


class ProjectManifest(NTruthModel):
    """Manifest del progetto: riapribile offline senza perdita (PRD FR-001)."""

    project_id: str
    name: str
    domain: str = "quantitative_microscopy"
    language: str = "en"
    created_at: str | None = None
    schema_version: str
    files: tuple[ProjectFile, ...] = ()
    experiment_bundles: tuple[ExperimentBundleManifest, ...] = ()
    ruleset_id: str = "ntruth-core"
    ruleset_version: str = "0.1.0"
    notes: str = ""
    integrity: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_files(self) -> ProjectManifest:
        ids = [f.file_id for f in self.files]
        if len(ids) != len(set(ids)):
            raise ValueError("file_id duplicati nel manifest di progetto")
        bundle_ids = [bundle.bundle_id for bundle in self.experiment_bundles]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("bundle_id duplicati nel manifest di progetto")
        known_files = set(ids)
        for bundle in self.experiment_bundles:
            missing = {ref.file_id for ref in bundle.files} - known_files
            if missing:
                raise ValueError(
                    f"Experiment Bundle {bundle.bundle_id} riferisce file sconosciuti: "
                    f"{sorted(missing)}"
                )
        return self

    def checksum(self) -> str:
        return content_checksum(
            {
                "project_id": self.project_id,
                # Licenza e governance sono parte dell'identita del progetto:
                # una variazione di consenso non puo lasciare invariato il checksum.
                "files": sorted(
                    (f.model_dump(mode="json") for f in self.files),
                    key=lambda item: str(item["file_id"]),
                ),
                "experiment_bundles": sorted(
                    (bundle.model_dump(mode="json") for bundle in self.experiment_bundles),
                    key=lambda item: str(item["bundle_id"]),
                ),
                "ruleset": (self.ruleset_id, self.ruleset_version),
                "schema_version": self.schema_version,
            }
        )
