"""Snapshot corpus e lineage riproducibile senza avviare alcun training."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum


class CorpusSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    EXTERNAL = "external"


class LeakageGroupKind(StrEnum):
    ARTICLE_FAMILY = "article_family"
    PREPRINT_VERSION = "preprint_version"
    CORRESPONDING_LAB = "corresponding_lab"
    LINKED_DATASET = "linked_dataset"
    SUPPLEMENT_FAMILY = "supplement_family"
    SYNTHETIC_TEMPLATE = "synthetic_template"


class CorpusAsset(FrozenModel):
    asset_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_id: str
    bundle_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: CorpusSplit
    leakage_group_ids: tuple[str, ...] = Field(min_length=1)
    synthetic: bool = False


class LeakageGroup(FrozenModel):
    group_id: str
    kind: LeakageGroupKind
    asset_ids: tuple[str, ...] = Field(min_length=1)


class CorpusSnapshotManifest(FrozenModel):
    """Manifest content-addressed; il medesimo contenuto produce il medesimo ID."""

    snapshot_id: str = ""
    parent_snapshot_ids: tuple[str, ...] = ()
    schema_version: str
    parser_contract_version: str
    guideline_version: str
    ontology_version: str
    assets: tuple[CorpusAsset, ...] = Field(min_length=1)
    leakage_groups: tuple[LeakageGroup, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> CorpusSnapshotManifest:
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asset_id duplicati nel corpus snapshot")
        group_ids = [group.group_id for group in self.leakage_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("leakage group duplicati nel corpus snapshot")
        asset_by_id = {asset.asset_id: asset for asset in self.assets}
        groups_by_id = {group.group_id: group for group in self.leakage_groups}
        for asset in self.assets:
            missing_groups = set(asset.leakage_group_ids) - groups_by_id.keys()
            if missing_groups:
                raise ValueError(
                    f"asset {asset.asset_id} riferisce leakage group assenti: "
                    f"{sorted(missing_groups)}"
                )
            if asset.synthetic and asset.split is not CorpusSplit.TRAIN:
                raise ValueError("asset sintetici ammessi soltanto nello split train")
        for group in self.leakage_groups:
            unknown = set(group.asset_ids) - asset_by_id.keys()
            if unknown:
                raise ValueError(f"leakage group riferisce asset assenti: {sorted(unknown)}")
            actual_members = {
                asset.asset_id for asset in self.assets if group.group_id in asset.leakage_group_ids
            }
            if actual_members != set(group.asset_ids):
                raise ValueError(f"membership non simmetrica per leakage group {group.group_id}")
            splits = {asset_by_id[asset_id].split for asset_id in group.asset_ids}
            if len(splits) > 1:
                raise ValueError(f"data leakage: gruppo {group.group_id} attraversa split distinti")
        expected_id = self.computed_snapshot_id()
        if self.snapshot_id and self.snapshot_id != expected_id:
            raise ValueError("snapshot_id non coerente con il contenuto")
        object.__setattr__(self, "snapshot_id", expected_id)
        if self.snapshot_id in self.parent_snapshot_ids:
            raise ValueError("un corpus snapshot non puo essere padre di se stesso")
        return self

    def _identity_payload(self) -> dict[str, object]:
        return {
            "parents": sorted(self.parent_snapshot_ids),
            "schema_version": self.schema_version,
            "parser_contract_version": self.parser_contract_version,
            "guideline_version": self.guideline_version,
            "ontology_version": self.ontology_version,
            "assets": sorted(
                (asset.model_dump(mode="json") for asset in self.assets),
                key=lambda item: str(item["asset_id"]),
            ),
            "leakage_groups": sorted(
                (group.model_dump(mode="json") for group in self.leakage_groups),
                key=lambda item: str(item["group_id"]),
            ),
        }

    def snapshot_checksum(self) -> str:
        return content_checksum(self._identity_payload())

    def computed_snapshot_id(self) -> str:
        return f"corpus-{self.snapshot_checksum()[:20]}"


class RunPurpose(StrEnum):
    INFERENCE = "inference"
    EVALUATION = "evaluation"
    TRAINING_DECLARATION = "training_declaration"


class ModelRunLineage(FrozenModel):
    """Lineage dichiarativa; non contiene ne avvia codice di training."""

    run_id: str
    purpose: RunPurpose
    parser_contract_version: str
    model_name: str
    model_version: str
    model_config_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_snapshot_id: str
    corpus_snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_splits: tuple[CorpusSplit, ...] = ()
    schema_version: str
    guideline_version: str
    ontology_version: str
    code_lock_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int | None = None

    def lineage_checksum(self) -> str:
        return content_checksum(self.model_dump(mode="json"))


def validate_snapshot_dag(snapshots: Iterable[CorpusSnapshotManifest]) -> None:
    """Rifiuta parent sconosciuti e cicli nella lineage fornita."""

    snapshot_list = list(snapshots)
    by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshot_list}
    if len(by_id) != len(snapshot_list):
        raise ValueError("snapshot_id duplicati nella lineage")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(snapshot_id: str) -> None:
        if snapshot_id in visiting:
            raise ValueError(f"ciclo nella lineage corpus a {snapshot_id}")
        if snapshot_id in visited:
            return
        snapshot = by_id[snapshot_id]
        visiting.add(snapshot_id)
        for parent_id in snapshot.parent_snapshot_ids:
            if parent_id not in by_id:
                raise ValueError(f"parent snapshot sconosciuto: {parent_id}")
            visit(parent_id)
        visiting.remove(snapshot_id)
        visited.add(snapshot_id)

    for current_id in by_id:
        visit(current_id)
