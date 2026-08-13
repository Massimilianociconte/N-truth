"""Tests for CRAFT PMCID discovery and official 67/30 partition validation."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from ntruth.data.config import CRAFT_VERSION, get_manifests_dir
from ntruth.data.datasets.craft import (
    CRAFTError,
    craft_annotation_policy,
    extract_craft_article_id,
    install_craft,
    load_craft_official_split,
    parse_craft_coreference,
)
from ntruth.data.splits import load_craft_2019_shared_task_split


def test_extract_craft_article_id():
    assert extract_craft_article_id(Path("corpus/PMC1134658.txt")) == "PMC1134658"
    assert extract_craft_article_id(Path("concept_annotations/PMC1247630.xml")) == "PMC1247630"


def test_load_craft_2019_shared_task_split():
    manifest_path = get_manifests_dir() / "craft_shared_task_2019_split.json"
    authority, split_map = load_craft_2019_shared_task_split(manifest_path)
    assert authority == "craft_shared_task_2019"
    assert len(split_map) == 97

    train_count = sum(1 for s in split_map.values() if s == "train")
    val_count = sum(1 for s in split_map.values() if s == "validation")
    test_count = sum(1 for s in split_map.values() if s == "test")

    assert train_count + val_count == 67
    assert test_count == 30


def test_load_craft_official_split_from_upstream_identifier_files(tmp_path: Path):
    ids = tmp_path / "articles" / "ids"
    ids.mkdir(parents=True)
    (ids / "craft-idmappings.txt").write_text(
        "#Format: [FILE NAME] <tab> [PMCID] <tab> [PMID]\n"
        "one.nxml\tPMC1\t1\n"
        "two.nxml\tPMC2\t2\n"
        "three.nxml\tPMC3\t3\n"
    )
    (ids / "craft-ids-train.txt").write_text("1\n")
    (ids / "craft-ids-dev.txt").write_text("2\n")
    (ids / "craft-ids-test.txt").write_text("3\n")

    authority, split_map, evidence = load_craft_official_split(tmp_path)

    assert authority == "craft_shared_task_2019"
    assert split_map == {"PMC1": "train", "PMC2": "validation", "PMC3": "test"}
    assert evidence["source_counts"] == {"train": 1, "validation": 1, "test": 1}


def test_parse_craft_coreference_emits_real_mentions_and_chains(tmp_path: Path):
    text = "Alpha cells activate them."
    annotation = tmp_path / "1.xml"
    annotation.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<knowtator-project>
  <document id="1" text-file="1.txt">
    <annotation annotator="Annotator" id="chain-1" type="identity">
      <class id="IDENTITY chain" label="IDENTITY chain"/>
      <span end="11" id="chain-span" start="0">Alpha cells</span>
    </annotation>
    <annotation annotator="Annotator" id="mention-1" type="identity">
      <class id="Noun Phrase" label="Noun Phrase"/>
      <span end="11" id="mention-span-1" start="0">Alpha cells</span>
    </annotation>
    <annotation annotator="Annotator" id="mention-2" type="identity">
      <class id="Noun Phrase" label="Noun Phrase"/>
      <span end="25" id="mention-span-2" start="21">them</span>
    </annotation>
    <graph-space id="Old Knowtator Relations">
      <vertex annotation="chain-1" id="node-chain"/>
      <vertex annotation="mention-1" id="node-1"/>
      <vertex annotation="mention-2" id="node-2"/>
      <triple annotator="Annotator" id="edge-1" object="node-1"
              property="Coreferring strings" subject="node-chain"/>
      <triple annotator="Annotator" id="edge-2" object="node-2"
              property="Coreferring strings" subject="node-chain"/>
    </graph-space>
  </document>
</knowtator-project>
""",
        encoding="utf-8",
    )

    payload, report = parse_craft_coreference(annotation, text)

    assert [mention.model_dump() for mention in payload.mentions] == [
        {"mention_id": "mention-1", "start": 0, "end": 11, "text": "Alpha cells"},
        {"mention_id": "mention-2", "start": 21, "end": 25, "text": "them"},
    ]
    assert [chain.model_dump() for chain in payload.chains] == [
        {"chain_id": "chain-1", "mention_ids": ["mention-1", "mention-2"]}
    ]
    assert report == {
        "upstream_chains": 1,
        "upstream_members": 2,
        "emitted_chains": 1,
        "emitted_mentions": 2,
        "excluded_chains": 0,
        "exclusion_reasons": {},
    }


def test_parse_craft_coreference_reports_lossy_unsupported_chains(tmp_path: Path):
    text = "Alpha cells activate them and beta cells."
    annotation = tmp_path / "1.xml"
    annotation.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<knowtator-project>
  <document id="1" text-file="1.txt">
    <annotation id="safe-chain"><class label="IDENTITY chain"/></annotation>
    <annotation id="safe-1"><class label="Noun Phrase"/><span start="0" end="11">Alpha cells</span></annotation>
    <annotation id="safe-2"><class label="Noun Phrase"/><span start="21" end="25">them</span></annotation>
    <annotation id="lossy-chain"><class label="IDENTITY chain"/></annotation>
    <annotation id="discontinuous"><class label="Noun Phrase"/><span start="0" end="5">Alpha</span><span start="30" end="34">beta</span></annotation>
    <annotation id="apposition"><class label="APPOS relation"/><span start="30" end="40">beta cells</span></annotation>
    <graph-space>
      <vertex annotation="safe-chain" id="safe-chain-node"/>
      <vertex annotation="safe-1" id="safe-node-1"/>
      <vertex annotation="safe-2" id="safe-node-2"/>
      <vertex annotation="lossy-chain" id="lossy-chain-node"/>
      <vertex annotation="discontinuous" id="discontinuous-node"/>
      <vertex annotation="apposition" id="apposition-node"/>
      <triple object="safe-node-1" property="Coreferring strings" subject="safe-chain-node"/>
      <triple object="safe-node-2" property="Coreferring strings" subject="safe-chain-node"/>
      <triple object="discontinuous-node" property="Coreferring strings" subject="lossy-chain-node"/>
      <triple object="apposition-node" property="Coreferring strings" subject="lossy-chain-node"/>
    </graph-space>
  </document>
</knowtator-project>
""",
        encoding="utf-8",
    )

    payload, report = parse_craft_coreference(annotation, text)

    assert [chain.chain_id for chain in payload.chains] == ["safe-chain"]
    assert [mention.mention_id for mention in payload.mentions] == ["safe-1", "safe-2"]
    assert report["upstream_chains"] == 2
    assert report["upstream_members"] == 4
    assert report["emitted_chains"] == 1
    assert report["excluded_chains"] == 1
    assert report["exclusion_reasons"] == {"discontinuous_mention": 1}


def test_parse_craft_coreference_fails_closed_on_offset_text_mismatch(tmp_path: Path):
    annotation = tmp_path / "1.xml"
    annotation.write_text(
        """<knowtator-project><document id="1">
<annotation id="chain"><class label="IDENTITY chain"/></annotation>
<annotation id="one"><class label="Noun Phrase"/><span start="0" end="5">WRONG</span></annotation>
<annotation id="two"><class label="Noun Phrase"/><span start="6" end="10">beta</span></annotation>
<graph-space>
<vertex annotation="chain" id="chain-node"/><vertex annotation="one" id="one-node"/><vertex annotation="two" id="two-node"/>
<triple object="one-node" property="Coreferring strings" subject="chain-node"/>
<triple object="two-node" property="Coreferring strings" subject="chain-node"/>
</graph-space></document></knowtator-project>""",
        encoding="utf-8",
    )

    with pytest.raises(CRAFTError, match="span text does not match source text"):
        parse_craft_coreference(annotation, "alpha beta")


def test_craft_annotation_policy_blocks_lossy_conversion():
    eligibility, native_tier, annotation_status = craft_annotation_policy(
        "train",
        {
            "upstream_chains": 2,
            "upstream_members": 4,
            "emitted_chains": 1,
            "emitted_mentions": 2,
            "excluded_chains": 1,
            "exclusion_reasons": {"discontinuous_mention": 1},
        },
    )

    assert eligibility.model_dump() == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": True,
    }
    assert native_tier.value == "HUMAN_CURATED_PARTIAL"
    assert annotation_status == "partial_annotation_conversion"


def test_craft_annotation_policy_blocks_empty_annotations():
    eligibility, native_tier, annotation_status = craft_annotation_policy(
        "train",
        {
            "upstream_chains": 0,
            "upstream_members": 0,
            "emitted_chains": 0,
            "emitted_mentions": 0,
            "excluded_chains": 0,
            "exclusion_reasons": {},
        },
    )

    assert eligibility.model_dump() == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": True,
    }
    assert native_tier.value == "MISSING_ANNOTATION"
    assert annotation_status == "empty_annotation"


@pytest.mark.parametrize("split", ["train", "validation", "test"])
def test_craft_annotation_policy_keeps_lossless_processed_records_model_ineligible(
    split: str,
):
    eligibility, native_tier, annotation_status = craft_annotation_policy(
        split,
        {
            "upstream_chains": 1,
            "upstream_members": 2,
            "emitted_chains": 1,
            "emitted_mentions": 2,
            "excluded_chains": 0,
            "exclusion_reasons": {},
        },
    )

    assert eligibility.model_dump() == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
    }
    assert native_tier.value == "HUMAN_CURATED_GOLD"
    assert annotation_status == "annotated"


def test_install_craft_never_emits_empty_gold_coreference_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    raw_root = tmp_path / "raw" / "craft" / CRAFT_VERSION
    ids_dir = raw_root / "articles" / "ids"
    text_dir = raw_root / "articles" / "txt"
    coreference_dir = raw_root / "coreference-annotation" / "knowtator-2"
    ids_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    coreference_dir.mkdir(parents=True)
    (raw_root / ".ntruth_complete.json").write_text("{}", encoding="utf-8")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    archive = downloads / f"craft-{CRAFT_VERSION}.zip"
    archive.write_bytes(b"pinned test archive")
    monkeypatch.setattr(
        "ntruth.data.datasets.craft.ensure_pinned_archive",
        lambda *_args, **_kwargs: "pinned",
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.craft.ensure_pinned_archive_verified_copy",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.craft.resume_marker_matches",
        lambda *_args, **_kwargs: True,
    )

    mapping_lines = ["#Format: filename <tab> PMCID <tab> PMID"]
    train_pmids = [str(number) for number in range(1, 61)]
    dev_pmids = [str(number) for number in range(61, 68)]
    test_pmids = [str(number) for number in range(68, 98)]
    text = "Alpha cells activate them."

    for pmid in train_pmids + dev_pmids + test_pmids:
        mapping_lines.append(f"{pmid}.nxml\tPMC{pmid}\t{pmid}")
        (text_dir / f"{pmid}.txt").write_text(text, encoding="utf-8")
        lossy_annotations = ""
        lossy_graph = ""
        if pmid == "1":
            lossy_annotations = (
                '<annotation id="lossy-chain"><class label="IDENTITY chain"/></annotation>'
                '<annotation id="apposition"><class label="APPOS relation"/>'
                '<span start="0" end="11">Alpha cells</span></annotation>'
            )
            lossy_graph = (
                '<vertex annotation="lossy-chain" id="lossy-chain-node"/>'
                '<vertex annotation="apposition" id="apposition-node"/>'
                '<triple object="apposition-node" property="Coreferring strings" '
                'subject="lossy-chain-node"/>'
            )
        (coreference_dir / f"{pmid}.xml").write_text(
            f"""<knowtator-project><document id="{pmid}">
<annotation id="chain"><class label="IDENTITY chain"/></annotation>
<annotation id="one"><class label="Noun Phrase"/><span start="0" end="11">Alpha cells</span></annotation>
<annotation id="two"><class label="Noun Phrase"/><span start="21" end="25">them</span></annotation>
{lossy_annotations}<graph-space>
<vertex annotation="chain" id="chain-node"/><vertex annotation="one" id="one-node"/><vertex annotation="two" id="two-node"/>
<triple object="one-node" property="Coreferring strings" subject="chain-node"/>
<triple object="two-node" property="Coreferring strings" subject="chain-node"/>
{lossy_graph}</graph-space></document></knowtator-project>""",
            encoding="utf-8",
        )

    (ids_dir / "craft-idmappings.txt").write_text("\n".join(mapping_lines) + "\n", encoding="utf-8")
    (ids_dir / "craft-ids-train.txt").write_text("\n".join(train_pmids) + "\n", encoding="utf-8")
    (ids_dir / "craft-ids-dev.txt").write_text("\n".join(dev_pmids) + "\n", encoding="utf-8")
    (ids_dir / "craft-ids-test.txt").write_text("\n".join(test_pmids) + "\n", encoding="utf-8")

    report = install_craft(tmp_path)

    train_records = [
        json.loads(line)
        for line in (tmp_path / "processed" / "craft" / CRAFT_VERSION / "train" / "records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    lossy_record = next(record for record in train_records if record["record_id"] == "craft:PMC1")
    safe_record = next(record for record in train_records if record["record_id"] == "craft:PMC2")

    assert len(lossy_record["payload"]["mentions"]) == 2
    assert len(lossy_record["payload"]["chains"]) == 1
    assert lossy_record["native_annotation_tier"] == "HUMAN_CURATED_PARTIAL"
    assert lossy_record["annotation_status"] == "partial_annotation_conversion"
    assert lossy_record["eligibility"] == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": True,
    }
    assert len(safe_record["payload"]["mentions"]) == 2
    assert len(safe_record["payload"]["chains"]) == 1
    assert safe_record["eligibility"] == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
    }
    assert report["split_counts"] == {"train": 60, "validation": 7, "test": 30}
    assert report["annotation_conversion"]["review_required_records"] == 1
    assert report["annotation_conversion"]["training_eligible_records"] == 0
    assert report["annotation_conversion"]["evaluation_eligible_records"] == 0
    assert report["model_use_status"] == "BLOCKED"
    assert report["training_ready_status"] == "NOT_MATERIALIZED"
    assert report["annotation_conversion"]["exclusion_reasons"] == {"unsupported_member_class": 1}
