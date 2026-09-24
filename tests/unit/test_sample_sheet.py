"""Contratto SampleSheetSpec v6 e I/O CSV riproducibile."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.sample_sheet import (
    REQUIRED_HEADERS,
    SampleLifecycleStatus,
    SampleSheetRow,
    SampleSheetSpec,
    SampleSheetValidationError,
    generate_sample_sheet,
    load_sample_sheet,
    validate_sample_sheet,
    write_sample_sheet,
)
from ntruth.sample_sheet import io as sample_sheet_io


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_generator_and_loader_round_trip_canonical_template(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    row = SampleSheetRow(
        sample_id="S1",
        source_id=None,
        preparation_id=None,
        culture_id="C1",
        plate_id="P1",
        well_id="A01",
        factor_levels={
            "factor_level_treatment": "drug",
            "factor_level_genotype": "WT",
        },
        batch_id="B1",
        timepoint="24 h",
        endpoint_id="viability",
        lifecycle_status=SampleLifecycleStatus.OBSERVED,
        file_ref="sha256:abc",
    )

    generated = generate_sample_sheet(
        path,
        factor_names=("treatment", "genotype"),
        rows=(row,),
    )
    spec = load_sample_sheet(generated)

    assert spec.schema_version == "6.0"
    assert spec.factor_columns == ("factor_level_treatment", "factor_level_genotype")
    assert spec.rows == (row,)
    assert spec.content_sha256 is not None and len(spec.content_sha256) == 64
    assert set(REQUIRED_HEADERS).issubset(spec.headers)


def test_required_nullable_provenance_headers_accept_empty_values(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "minimal.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,,,vehicle,planned\n",
    )

    validation = validate_sample_sheet(path)

    assert validation.valid
    assert validation.spec is not None
    assert validation.spec.rows[0].source_id is None
    assert validation.spec.rows[0].preparation_id is None


@pytest.mark.parametrize("missing", REQUIRED_HEADERS)
def test_each_required_header_is_enforced(tmp_path: Path, missing: str) -> None:
    headers = [
        "sample_id",
        "source_id",
        "preparation_id",
        "factor_level_treatment",
        "lifecycle_status",
    ]
    headers.remove(missing)
    path = _write(tmp_path / f"missing-{missing}.csv", ",".join(headers) + "\n")

    validation = validate_sample_sheet(path)

    assert not validation.valid
    assert any(issue.code == "missing_required_header" for issue in validation.errors)
    with pytest.raises(SampleSheetValidationError):
        load_sample_sheet(path)


def test_at_least_one_named_factor_column_is_required(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "no-factor.csv",
        "sample_id,source_id,preparation_id,lifecycle_status\nS1,SRC1,P1,observed\n",
    )

    validation = validate_sample_sheet(path)

    assert not validation.valid
    assert {issue.code for issue in validation.errors} == {"missing_factor_header"}


def test_factor_value_is_required_for_every_row(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "missing-level.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,SRC1,P1,,observed\n",
    )

    validation = validate_sample_sheet(path)

    assert not validation.valid
    assert any(issue.code == "invalid_row" for issue in validation.errors)


def test_duplicate_sample_id_is_rejected_with_both_row_numbers(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "duplicate.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,SRC1,P1,drug,observed\n"
        "S1,SRC1,P1,vehicle,observed\n",
    )

    validation = validate_sample_sheet(path)

    duplicate = next(issue for issue in validation.errors if issue.code == "duplicate_sample_id")
    assert duplicate.row == 3
    assert "righe 2 e 3" in duplicate.message


def test_excluded_row_requires_reason_but_other_states_do_not(tmp_path: Path) -> None:
    invalid = _write(
        tmp_path / "excluded-invalid.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status,"
        "exclusion_reason\nS1,SRC1,P1,drug,excluded,\n",
    )
    valid = _write(
        tmp_path / "excluded-valid.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status,"
        "exclusion_reason\nS1,SRC1,P1,drug,excluded,QC failure before analysis\n"
        "S2,SRC2,P2,vehicle,observed,\n",
    )

    assert not validate_sample_sheet(invalid).valid
    assert load_sample_sheet(valid).rows[0].exclusion_reason == "QC failure before analysis"


def test_legacy_column_aliases_are_imported_but_reported(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "aliases.csv",
        "sample_id,source_id,preparation_id,factor_level,batch,endpoint,status\n"
        "S1,SRC1,P1,drug,B1,viability,observed\n",
    )

    validation = validate_sample_sheet(path)

    assert validation.valid
    assert validation.spec is not None
    assert validation.spec.factor_columns == ("factor_level_treatment",)
    assert validation.spec.rows[0].batch_id == "B1"
    assert validation.spec.rows[0].endpoint_id == "viability"
    assert {issue.code for issue in validation.warnings} == {"legacy_header_alias"}


def test_us_analyzed_is_read_but_serialized_as_normative_analysed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "spelling.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,SRC1,P1,drug,analyzed\n",
    )

    row = load_sample_sheet(path).rows[0]

    assert row.lifecycle_status is SampleLifecycleStatus.ANALYSED
    assert row.model_dump(mode="json")["lifecycle_status"] == "analysed"


def test_numeric_timepoint_without_unit_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "timepoint.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,timepoint,lifecycle_status\n"
        "S1,SRC1,P1,drug,24,observed\n",
    )

    validation = validate_sample_sheet(path)

    assert not validation.valid
    assert any("unita temporale" in issue.message for issue in validation.errors)


def test_direct_spec_rejects_factor_headers_incoherent_with_rows() -> None:
    row = SampleSheetRow(
        sample_id="S1",
        source_id=None,
        preparation_id=None,
        factor_levels={"factor_level_treatment": "drug"},
        lifecycle_status="planned",
    )

    with pytest.raises(ValidationError, match="factor_columns non coincide"):
        SampleSheetSpec(
            headers=(
                "sample_id",
                "source_id",
                "preparation_id",
                "factor_level_genotype",
                "lifecycle_status",
            ),
            factor_columns=("factor_level_treatment",),
            rows=(row,),
        )


def test_schema_has_no_field_that_can_assert_allocation_or_independence() -> None:
    forbidden = {
        "allocation_level",
        "assignment_level",
        "independently_assigned",
        "independence_mechanism",
    }

    assert forbidden.isdisjoint(SampleSheetRow.model_fields)
    assert forbidden.isdisjoint(SampleSheetSpec.model_fields)


def test_write_preserves_extension_columns_and_values(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "extended.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status,operator_role\n"
        "S1,SRC1,P1,drug,observed,facility_staff\n",
    )
    spec = load_sample_sheet(source)

    destination = write_sample_sheet(spec, tmp_path / "roundtrip.csv")
    reloaded = load_sample_sheet(destination)

    assert reloaded.headers == spec.headers
    assert reloaded.rows[0].extra_fields == {"operator_role": "facility_staff"}


def test_sample_sheet_input_rejects_symlink_and_bounded_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write(
        tmp_path / "target.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,SRC1,P1,drug,observed\n",
    )
    link = tmp_path / "linked.csv"
    link.symlink_to(target)

    linked = validate_sample_sheet(link)
    assert not linked.valid
    assert {issue.code for issue in linked.errors} == {"symlink_not_allowed"}

    monkeypatch.setattr(sample_sheet_io, "MAX_SAMPLE_SHEET_BYTES", 16)
    oversized = validate_sample_sheet(target)
    assert not oversized.valid
    assert {issue.code for issue in oversized.errors} == {"file_too_large"}


def test_sample_sheet_row_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(
        tmp_path / "rows.csv",
        "sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status\n"
        "S1,SRC1,P1,drug,observed\n"
        "S2,SRC2,P2,vehicle,observed\n",
    )
    monkeypatch.setattr(sample_sheet_io, "MAX_SAMPLE_SHEET_ROWS", 1)

    validation = validate_sample_sheet(path)

    assert not validation.valid
    assert {issue.code for issue in validation.errors} == {"too_many_rows"}


def test_sample_sheet_force_never_follows_destination_symlink(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("do not overwrite", encoding="utf-8")
    destination = tmp_path / "samples.csv"
    destination.symlink_to(victim)

    with pytest.raises(OSError, match="symlink"):
        generate_sample_sheet(destination, overwrite=True)

    assert victim.read_text(encoding="utf-8") == "do not overwrite"
    assert destination.is_symlink()


def test_extra_fields_cannot_override_canonical_sample_sheet_values() -> None:
    with pytest.raises(ValidationError, match="extra_fields non puo ridefinire"):
        SampleSheetRow(
            sample_id="S1",
            source_id="SRC1",
            preparation_id="P1",
            factor_levels={"factor_level_treatment": "drug"},
            lifecycle_status="observed",
            extra_fields={"sample_id": "S_OTHER"},
        )
