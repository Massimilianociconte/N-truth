"""Checksum-verified packaged JSON Schema snapshot for the PRD v8 kernel."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

KERNEL_SCHEMA_SNAPSHOT_FILENAME = "prd-v8-kernel-schemas-8.0.0.json"


def _snapshot_checksum(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class KernelSchemaSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["8.0.0"] = "8.0.0"
    snapshot_id: str
    generated_from: Literal["ntruth.schemas.kernel.kernel_json_schemas"]
    schemas: dict[str, dict[str, Any]]
    declared_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"snapshot_id", "declared_checksum"})
        checksum = _snapshot_checksum(payload)
        if self.declared_checksum != checksum:
            raise ValueError("kernel schema snapshot checksum mismatch")
        if self.snapshot_id != f"KERNEL-SCHEMAS-{checksum[:20]}":
            raise ValueError("kernel schema snapshot ID mismatch")
        return self


def build_kernel_schema_snapshot() -> KernelSchemaSnapshot:
    from ntruth.schemas.kernel import kernel_json_schemas

    fields: dict[str, Any] = {
        "schema_version": "8.0.0",
        "generated_from": "ntruth.schemas.kernel.kernel_json_schemas",
        "schemas": kernel_json_schemas(),
    }
    checksum = _snapshot_checksum(fields)
    addressed = {**fields, "snapshot_id": f"KERNEL-SCHEMAS-{checksum[:20]}"}
    return KernelSchemaSnapshot(**addressed, declared_checksum=checksum)


def load_kernel_schema_snapshot_file(path: Path) -> KernelSchemaSnapshot:
    return KernelSchemaSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def load_installed_kernel_schema_snapshot() -> KernelSchemaSnapshot:
    resource = files("ntruth.schemas").joinpath("assets", KERNEL_SCHEMA_SNAPSHOT_FILENAME)
    return KernelSchemaSnapshot.model_validate_json(resource.read_text(encoding="utf-8"))


__all__ = [
    "KERNEL_SCHEMA_SNAPSHOT_FILENAME",
    "KernelSchemaSnapshot",
    "build_kernel_schema_snapshot",
    "load_installed_kernel_schema_snapshot",
    "load_kernel_schema_snapshot_file",
]
