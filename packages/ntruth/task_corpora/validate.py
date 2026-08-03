"""Fail-closed validators for task records and BIO sequences."""

from __future__ import annotations

from ntruth.task_corpora.authority import ExclusionReason
from ntruth.task_corpora.schemas import TaskRecord


class ValidationError(RuntimeError):
    """Structural validation failure."""

    def __init__(self, reason: ExclusionReason | str, detail: str = "") -> None:
        self.reason = str(reason)
        self.detail = detail
        super().__init__(f"{self.reason}: {detail}" if detail else self.reason)


def assert_token_label_lengths(tokens: list[str], *label_seqs: list[str]) -> None:
    n = len(tokens)
    if n == 0:
        raise ValidationError(ExclusionReason.EMPTY_RECORD, "empty tokens")
    for labels in label_seqs:
        if len(labels) != n:
            raise ValidationError(
                ExclusionReason.TOKEN_LABEL_LENGTH_MISMATCH,
                f"len(labels)={len(labels)} len(tokens)={n}",
            )


def assert_bio_tags_known(labels: list[str], allowed_types: set[str]) -> list[str]:
    """Return list of unknown full tags (B-X / I-X / O)."""
    unknown: list[str] = []
    for tag in labels:
        if tag == "O":
            continue
        if "-" not in tag:
            unknown.append(tag)
            continue
        prefix, typ = tag.split("-", 1)
        if prefix not in {"B", "I"} or typ not in allowed_types:
            unknown.append(tag)
    return unknown


def validate_task_record(record: TaskRecord) -> None:
    """Raise ValidationError if record violates hard invariants (beyond pydantic)."""
    try:
        # re-run pydantic-level invariants already on model; extra checks:
        if record.checksum == "":
            raise ValidationError(ExclusionReason.INVALID_CHECKSUM, "empty checksum")
        if not record.transform_lineage.parent_checksum:
            raise ValidationError(ExclusionReason.INCOMPLETE_LINEAGE, "parent_checksum")
    except ValidationError:
        raise
    except Exception as exc:  # pragma: no cover
        raise ValidationError(ExclusionReason.MALFORMED_SOURCE, str(exc)) from exc
