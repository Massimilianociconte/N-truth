"""Factory sintetica graph-first per snapshot P0-alpha (esperimento, non scienza).

Flusso: canonical graph → observation → renderer → stage target → validate.

I 39 casi B4_CONSTRAINED_DEV sono generator-inaccessible: i loro testi non
possono entrare in train/val (gate similarità).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ntruth.model_backends.stage_schemas import (
    CandidateRelationStage,
    CountMini,
    EndpointMini,
    EntityCountStage,
    EntityMini,
    EvidenceExtractionStage,
    EvidenceSpanMini,
    FactorMini,
    MinimalCandidateGraphStage,
    RelationMini,
    StageProvenanceMini,
)
from ntruth.training.mlx_dataset import SYSTEM_PROMPT

P0_TASKS = (
    "TASK_EVIDENCE",
    "TASK_ENTITY_COUNT",
    "TASK_FACTOR_ENDPOINT",
    "TASK_EXPLICIT_RELATIONS",
)

RENDERER_VERSION = "p0-graph-first-1.0.0"
SCHEMA_VERSION = "1.0.0"
SNAPSHOT_SCHEMA = "p0-alpha-1.0.0"


@dataclass(frozen=True)
class CanonicalGraph:
    family_id: str
    entities: tuple[tuple[str, str], ...]  # (label, node_type)
    count: tuple[str, int | None, str] | None  # (quantifier, value, unit_label)
    factor: tuple[str, tuple[str, ...]] | None  # (name, levels)
    endpoint: str | None
    relation: tuple[str, str, str] | None  # (src_label, rel, tgt_label)
    template_id: str


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _graph_hash(graph: CanonicalGraph) -> str:
    payload = {
        "family_id": graph.family_id,
        "entities": list(graph.entities),
        "count": graph.count,
        "factor": graph.factor,
        "endpoint": graph.endpoint,
        "relation": graph.relation,
        "template_id": graph.template_id,
    }
    return _sha(json.dumps(payload, sort_keys=True, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Graph families (seed templates) — ~50 families × variants = 2k examples
# ---------------------------------------------------------------------------


def _base_families() -> list[CanonicalGraph]:
    specs: list[tuple[str, tuple[tuple[str, str], ...], Any, Any, Any, Any]] = [
        (
            "donors_cells",
            (("donors", "HumanDonor"), ("cells", "Cell")),
            ("EXACT", 5, "HumanDonor"),
            ("treatment", ("LPS", "vehicle")),
            "marker intensity",
            ("cells", "derived_from", "donors"),
        ),
        (
            "animals_cages",
            (("animals", "Animal"), ("cages", "Cage")),
            ("EXACT", 12, "Animal"),
            ("diet", ("high-fat", "control")),
            "body weight",
            ("animals", "nested_in", "cages"),
        ),
        (
            "wells_plates",
            (("wells", "Well"), ("plates", "Plate")),
            ("EXACT", 96, "Well"),
            ("drug", ("A", "B")),
            "viability",
            ("wells", "nested_in", "plates"),
        ),
        (
            "organoids_lines",
            (("organoids", "Organoid"), ("iPSC lines", "CellLine")),
            ("EXACT", 3, "CellLine"),
            ("stimulus", ("low", "high")),
            "spike rate",
            ("organoids", "derived_from", "iPSC lines"),
        ),
        (
            "cultures_wells",
            (("primary cultures", "PrimaryCulture"), ("wells", "Well")),
            ("EXACT", 4, "Well"),
            ("compound", ("X", "vehicle")),
            "synaptic density",
            ("wells", "derived_from", "primary cultures"),
        ),
        (
            "sections_rois",
            (("tissue sections", "Section_"), ("ROIs", "ROI")),
            ("EXACT", 6, "Animal"),
            None,
            "mean fluorescence",
            ("ROIs", "nested_in", "tissue sections"),
        ),
        (
            "batches_aliquots",
            (("batches", "Batch"), ("aliquots", "Aliquot")),
            ("EXACT", 8, "Aliquot"),
            None,
            None,
            ("aliquots", "nested_in", "batches"),
        ),
        (
            "images_fields",
            (("images", "Image"), ("fields", "Field")),
            ("EXACT", 20, "Field"),
            None,
            "object counts",
            ("fields", "nested_in", "images"),
        ),
        (
            "litters_offspring",
            (("litters", "Litter"), ("offspring", "Animal")),
            ("EXACT", 10, "Litter"),
            ("weaning", ("early", "late")),
            "latency",
            ("offspring", "nested_in", "litters"),
        ),
        (
            "dams_explants",
            (("dams", "Dam"), ("explants", "Explant")),
            ("EXACT", 2, "Dam"),
            ("treatment", ("Y", "control")),
            "outgrowth length",
            ("explants", "derived_from", "dams"),
        ),
        (
            "patients_sections",
            (("patients", "HumanDonor"), ("sections", "Section_")),
            ("EXACT", 24, "HumanDonor"),
            None,
            "H-score",
            ("sections", "nested_in", "patients"),
        ),
        (
            "libraries_samples",
            (("libraries", "Library"), ("primary samples", "PrimarySample")),
            ("EXACT", 8, "Library"),
            None,
            None,
            ("libraries", "derived_from", "primary samples"),
        ),
        (
            "mice_diet",
            (("mice", "Animal"),),
            ("EXACT", 18, "Animal"),
            ("diet", ("chow", "high-fat")),
            "body weight",
            None,
        ),
        (
            "empty_methods",
            (),
            None,
            None,
            None,
            None,
        ),
        (
            "count_range_cages",
            (("cages", "Cage"),),
            ("RANGE", None, "Cage"),  # value filled in variant
            ("diet", ("A", "B")),
            None,
            None,
        ),
        (
            "count_approx_cells",
            (("cells", "Cell"),),
            ("APPROXIMATE", 200, "Cell"),
            None,
            "intensity",
            None,
        ),
        (
            "count_unknown",
            (("technical replicates", "Cell"),),
            ("NOT_REPORTED", None, "Cell"),
            None,
            None,
            None,
        ),
        (
            "cell_line_drug",
            (("cell lines", "CellLine"), ("wells", "Well"), ("plates", "Plate")),
            None,
            ("drug_z", ("0 uM", "1 uM", "10 uM")),
            "IC50",
            ("wells", "nested_in", "plates"),
        ),
    ]
    families: list[CanonicalGraph] = []
    for fid, ents, count, factor, endpoint, rel in specs:
        # fix wells_plates relation target if plates missing from entities for cell_line
        families.append(
            CanonicalGraph(
                family_id=f"fam-{fid}",
                entities=ents,
                count=count,
                factor=factor,
                endpoint=endpoint,
                relation=rel,
                template_id=fid,
            )
        )
    # Expand with numeric variants of core families
    extra: list[CanonicalGraph] = []
    for n, unit_label, ntype in (
        (3, "donors", "HumanDonor"),
        (6, "animals", "Animal"),
        (8, "wells", "Well"),
        (15, "fields", "Field"),
        (4, "batches", "Batch"),
        (10, "organoids", "Organoid"),
        (7, "cages", "Cage"),
        (9, "mice", "Animal"),
    ):
        extra.append(
            CanonicalGraph(
                family_id=f"fam-n{n}-{ntype.lower()}",
                entities=((unit_label, ntype),),
                count=("EXACT", n, ntype),
                factor=None,
                endpoint=None,
                relation=None,
                template_id=f"count_only_{n}",
            )
        )
    # Relation-focused families
    for src, rel, tgt, st, tt in (
        ("cells", "nested_in", "wells", "Cell", "Well"),
        ("images", "derived_from", "wells", "Image", "Well"),
        ("ROIs", "nested_in", "images", "ROI", "Image"),
        ("aliquots", "nested_in", "batches", "Aliquot", "Batch"),
        ("libraries", "derived_from", "samples", "Library", "PrimarySample"),
        ("wells", "nested_in", "plates", "Well", "Plate"),
        ("sections", "derived_from", "animals", "Section_", "Animal"),
        ("fields", "nested_in", "wells", "Field", "Well"),
    ):
        extra.append(
            CanonicalGraph(
                family_id=f"fam-rel-{src}-{rel}-{tgt}",
                entities=((src, st), (tgt, tt)),
                count=None,
                factor=None,
                endpoint=None,
                relation=(src, rel, tgt),
                template_id=f"rel_{rel}",
            )
        )
    return families + extra


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


_ACTIVE = (
    "{entity} were obtained from the study material.",
    "{entity} were prepared according to the protocol.",
    "We used {entity} for the experiment.",
)
_PASSIVE = (
    "{entity} were collected.",
    "{entity} were allocated as described below.",
)
_COUNT_EXACT = (
    "A total of {n} {unit} were used (n = {n}).",
    "The study included {n} {unit}.",
    "n = {n} {unit}.",
)
_COUNT_APPROX = (
    "Approximately {n} {unit} were imaged.",
    "About {n} {unit} were analysed.",
)
_COUNT_RANGE = (
    "Between {lo} and {hi} {unit} were assigned per arm.",
    "{lo}-{hi} {unit} were used.",
)
_COUNT_NR = (
    "The number of {unit} was not reported.",
    "n for {unit} was not reported.",
)
_FACTOR = (
    "{name} ({levels}) was applied.",
    "Groups received {name}: {levels}.",
)
_ENDPOINT = (
    "{endpoint} was quantified.",
    "The primary endpoint was {endpoint}.",
)
_REL_NESTED = (
    "{src} were nested in {tgt}.",
    "Each {src_sing} was nested within a {tgt_sing}.",
)
_REL_DERIVED = (
    "{src} were derived from {tgt}.",
    "{src} were obtained from {tgt}.",
)
_DISTRACTOR = (
    "Buffers were prepared weekly.",
    "Room temperature was maintained at 22 C.",
    "Software version 1.2 was used for acquisition.",
)


def _singular(label: str) -> str:
    if label.endswith("ies"):
        return label[:-3] + "y"
    if label.endswith("s") and not label.endswith("ss"):
        return label[:-1]
    return label


def render_text(
    graph: CanonicalGraph,
    *,
    rng: random.Random,
    style: Literal["active", "passive", "mixed"] = "mixed",
    include_distractor: bool = False,
    invert_order: bool = False,
    empty_force: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Ritorna (text, observation) con indici span per i fatti emessi."""

    if empty_force or (
        not graph.entities and not graph.count and not graph.factor and not graph.relation
    ):
        text = rng.choice(
            (
                "No experimental methods are described in this fragment.",
                "Supplementary material contains only figure layouts.",
                "Abstract only; methods section missing.",
            )
        )
        return text, {"spans": [], "visible": {}}

    clauses: list[str] = []
    observation: dict[str, Any] = {"spans": [], "visible": {}}

    def add_clause(template: str, **kwargs: str) -> str:
        clause = template.format(**kwargs)
        clauses.append(clause)
        return clause

    # Entities
    for label, ntype in graph.entities:
        pool = _ACTIVE if style != "passive" else _PASSIVE
        if style == "mixed":
            pool = _ACTIVE + _PASSIVE
        clause = add_clause(rng.choice(pool), entity=label)
        observation["visible"].setdefault("entities", []).append(
            {"label": label, "node_type": ntype, "clause": clause}
        )

    # Count
    if graph.count is not None:
        quant, value, unit = graph.count
        unit_word = graph.entities[0][0] if graph.entities else unit
        if quant == "EXACT" and value is not None:
            clause = add_clause(
                rng.choice(_COUNT_EXACT), n=str(value), unit=unit_word
            )
            observation["visible"]["count"] = {
                "quantifier": "EXACT",
                "value": value,
                "unit_label": unit,
                "clause": clause,
            }
        elif quant == "APPROXIMATE" and value is not None:
            clause = add_clause(
                rng.choice(_COUNT_APPROX), n=str(value), unit=unit_word
            )
            observation["visible"]["count"] = {
                "quantifier": "APPROXIMATE",
                "value": value,
                "unit_label": unit,
                "clause": clause,
            }
        elif quant == "RANGE":
            lo, hi = 8, 10
            if value is not None:
                lo, hi = max(1, value - 1), value + 1
            clause = add_clause(
                rng.choice(_COUNT_RANGE), lo=str(lo), hi=str(hi), unit=unit_word
            )
            observation["visible"]["count"] = {
                "quantifier": "RANGE",
                "lower_bound": lo,
                "upper_bound": hi,
                "value": None,
                "unit_label": unit,
                "clause": clause,
            }
        elif quant == "NOT_REPORTED":
            clause = add_clause(rng.choice(_COUNT_NR), unit=unit_word)
            observation["visible"]["count"] = {
                "quantifier": "NOT_REPORTED",
                "value": None,
                "unit_label": unit,
                "clause": clause,
            }

    # Factor / endpoint
    if graph.factor is not None:
        name, levels = graph.factor
        levels_s = " or ".join(levels) if len(levels) == 2 else ", ".join(levels)
        clause = add_clause(rng.choice(_FACTOR), name=name, levels=levels_s)
        observation["visible"]["factor"] = {
            "name": name,
            "levels": list(levels),
            "clause": clause,
        }
    if graph.endpoint is not None:
        clause = add_clause(rng.choice(_ENDPOINT), endpoint=graph.endpoint)
        observation["visible"]["endpoint"] = {
            "name": graph.endpoint,
            "clause": clause,
        }

    # Relation
    if graph.relation is not None:
        src, rel, tgt = graph.relation
        pool = _REL_NESTED if rel == "nested_in" else _REL_DERIVED
        clause = add_clause(
            rng.choice(pool),
            src=src,
            tgt=tgt,
            src_sing=_singular(src),
            tgt_sing=_singular(tgt),
        )
        observation["visible"]["relation"] = {
            "source_label": src,
            "target_label": tgt,
            "relation_type": rel,
            "clause": clause,
        }

    if include_distractor:
        clauses.append(rng.choice(_DISTRACTOR))

    if invert_order and len(clauses) > 1:
        clauses = list(reversed(clauses))

    text = " ".join(clauses)
    # span indices from clauses present in final text
    spans = []
    for key in ("entities",):
        for item in observation["visible"].get(key) or []:
            clause = item["clause"]
            if clause in text:
                start = text.index(clause)
                # tighter span on entity label if possible
                lab = item["label"]
                if lab in text[start : start + len(clause)]:
                    rel = text[start : start + len(clause)].index(lab)
                    s0, s1 = start + rel, start + rel + len(lab)
                else:
                    s0, s1 = start, start + len(clause)
                spans.append(
                    {
                        "text": text[s0:s1],
                        "start": s0,
                        "end": s1,
                        "kind": "entity",
                        "meta": item,
                    }
                )
    for kind in ("count", "factor", "endpoint", "relation"):
        item = observation["visible"].get(kind)
        if not item:
            continue
        clause = item["clause"]
        if clause not in text:
            continue
        start = text.index(clause)
        spans.append(
            {
                "text": clause,
                "start": start,
                "end": start + len(clause),
                "kind": kind,
                "meta": item,
            }
        )
    observation["spans"] = spans
    return text, observation


# ---------------------------------------------------------------------------
# Stage targets
# ---------------------------------------------------------------------------


def _prov(stage: str, example_id: str) -> StageProvenanceMini:
    return StageProvenanceMini(
        stage_run_id=f"syn-{example_id}",
        stage=stage,
        authority="model",
        producer="p0-synthetic-gold",
        producer_version=RENDERER_VERSION,
    )


def build_targets(
    *,
    example_id: str,
    file_id: str,
    text: str,
    observation: dict[str, Any],
    graph: CanonicalGraph,
) -> dict[str, dict[str, Any]]:
    """Costruisce target per i quattro task; valida via Pydantic."""

    spans_by_kind: dict[str, list[dict[str, Any]]] = {}
    for sp in observation.get("spans") or []:
        spans_by_kind.setdefault(sp["kind"], []).append(sp)

    # Evidence: one span per observed fact
    evidence_items: list[EvidenceSpanMini] = []
    for i, sp in enumerate(observation.get("spans") or []):
        evidence_items.append(
            EvidenceSpanMini(
                evidence_id=f"ev-{example_id}-{i}",
                file_id=file_id,
                text=sp["text"],
                start=int(sp["start"]),
                end=int(sp["end"]),
                confidence=0.9,
            )
        )
    # map kind -> first evidence id
    kind_ev: dict[str, str] = {}
    for i, sp in enumerate(observation.get("spans") or []):
        kind_ev.setdefault(sp["kind"], f"ev-{example_id}-{i}")

    ev_target = EvidenceExtractionStage(
        result_id=f"res-ev-{example_id}",
        provenance=_prov("evidence_extraction", example_id),
        evidence_spans=evidence_items,
    )

    entities: list[EntityMini] = []
    for i, ent in enumerate((observation.get("visible") or {}).get("entities") or []):
        eid = kind_ev.get("entity", evidence_items[0].evidence_id if evidence_items else "")
        # prefer entity-specific evidence
        for j, sp in enumerate(observation.get("spans") or []):
            if sp["kind"] == "entity" and sp["meta"].get("label") == ent["label"]:
                eid = f"ev-{example_id}-{j}"
                break
        entities.append(
            EntityMini(
                node_id=f"node-{example_id}-{i}",
                label=ent["label"],
                node_type=ent["node_type"],
                evidence_ids=[eid] if eid else [],
                confidence=0.9,
            )
        )

    counts: list[CountMini] = []
    cvis = (observation.get("visible") or {}).get("count")
    if cvis:
        eid = kind_ev.get("count", evidence_items[0].evidence_id if evidence_items else "")
        kwargs: dict[str, Any] = {
            "count_id": f"count-{example_id}",
            "quantifier": cvis["quantifier"],
            "unit_label": cvis.get("unit_label") or "",
            "evidence_ids": [eid] if eid else [],
            "confidence": 0.9,
        }
        if cvis["quantifier"] in {"EXACT", "APPROXIMATE"}:
            kwargs["value"] = cvis.get("value")
        elif cvis["quantifier"] == "RANGE":
            kwargs["lower_bound"] = cvis.get("lower_bound")
            kwargs["upper_bound"] = cvis.get("upper_bound")
            kwargs["value"] = None
        counts.append(CountMini(**kwargs))

    ec_target = EntityCountStage(
        result_id=f"res-ec-{example_id}",
        provenance=_prov("entity_count", example_id),
        entities=entities,
        counts=counts,
    )

    relations: list[RelationMini] = []
    rvis = (observation.get("visible") or {}).get("relation")
    if rvis:
        eid = kind_ev.get("relation", evidence_items[0].evidence_id if evidence_items else "")
        relations.append(
            RelationMini(
                edge_id=f"edge-{example_id}",
                source_label=rvis["source_label"],
                target_label=rvis["target_label"],
                relation_type=rvis["relation_type"]
                if rvis["relation_type"] in {"nested_in", "derived_from"}
                else "other",
                evidence_ids=[eid] if eid else [],
                confidence=0.9,
            )
        )
    rel_target = CandidateRelationStage(
        result_id=f"res-rel-{example_id}",
        provenance=_prov("candidate_relations", example_id),
        relations=relations,
    )

    factors: list[FactorMini] = []
    fvis = (observation.get("visible") or {}).get("factor")
    if fvis:
        eid = kind_ev.get("factor", evidence_items[0].evidence_id if evidence_items else "")
        factors.append(
            FactorMini(
                factor_id=f"factor-{example_id}",
                name=fvis["name"],
                levels=list(fvis["levels"]),
                evidence_ids=[eid] if eid else [],
            )
        )
    endpoints: list[EndpointMini] = []
    evis = (observation.get("visible") or {}).get("endpoint")
    if evis:
        eid = kind_ev.get("endpoint", evidence_items[0].evidence_id if evidence_items else "")
        endpoints.append(
            EndpointMini(
                endpoint_id=f"endpoint-{example_id}",
                name=evis["name"],
                evidence_ids=[eid] if eid else [],
            )
        )

    # Factor/endpoint stage as MinimalCandidateGraphStage slice (task tag separate)
    fe_target = MinimalCandidateGraphStage(
        result_id=f"res-fe-{example_id}",
        graph_set_id=f"graph-fe-{example_id}",
        provenance=_prov("candidate_graph_set", example_id),
        experiment_block_title="synthetic block",
        evidence_spans=evidence_items,
        entities=entities,
        counts=counts,
        factors=factors,
        endpoints=endpoints,
        relations=relations,
        missing_fact_predicates=[],
    )

    return {
        "TASK_EVIDENCE": ev_target.model_dump(mode="json"),
        "TASK_ENTITY_COUNT": ec_target.model_dump(mode="json"),
        "TASK_EXPLICIT_RELATIONS": rel_target.model_dump(mode="json"),
        "TASK_FACTOR_ENDPOINT": fe_target.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# DEV protection
# ---------------------------------------------------------------------------


def load_dev_text_fingerprints(cases_path: Path) -> set[str]:
    fps: set[str] = set()
    if not cases_path.is_file():
        return fps
    with cases_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            case = json.loads(line)
            if case.get("split") != "eval":
                continue
            text = case.get("source_text") or ""
            fps.add(_sha(_norm(text)))
            # shingles for near match
            for sh in _shingles(_norm(text), 5):
                fps.add(f"sh:{sh}")
    return fps


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _shingles(text: str, k: int) -> set[str]:
    toks = text.split()
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def contaminates_dev(text: str, dev_fps: set[str], *, threshold: float = 0.35) -> bool:
    n = _norm(text)
    if _sha(n) in dev_fps:
        return True
    sh = _shingles(n, 5)
    if not sh:
        return False
    hits = sum(1 for s in sh if f"sh:{s}" in dev_fps)
    return (hits / len(sh)) >= threshold


# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------


def generate_p0_alpha_records(
    *,
    n_train: int = 2000,
    n_val: int = 300,
    seed: int = 13,
    dev_cases_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    families = _base_families()
    # Assign families to train/val without leakage
    fam_ids = [f.family_id for f in families]
    rng.shuffle(fam_ids)
    n_val_fam = max(1, len(fam_ids) // 5)
    val_fams = set(fam_ids[:n_val_fam])
    train_fams = set(fam_ids[n_val_fam:])
    by_id = {f.family_id: f for f in families}

    dev_fps = load_dev_text_fingerprints(
        dev_cases_path or Path("benchmarks/fewshot_p0/cases.jsonl")
    )

    rejection_log: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    seen_hash: set[str] = set()

    styles = ("active", "passive", "mixed")
    tasks = list(P0_TASKS)

    def make_one(
        graph: CanonicalGraph,
        split: str,
        idx: int,
        *,
        counterfactual: bool = False,
        empty_force: bool = False,
        negative_relation: bool = False,
    ) -> dict[str, Any] | None:
        style = rng.choice(styles)
        invert = rng.random() < 0.35
        distract = rng.random() < 0.25
        g = graph
        pert: list[str] = []
        if counterfactual and g.relation is not None:
            src, rel, tgt = g.relation
            # reverse direction counterfactual → still explicit but inverted labels swap
            g = CanonicalGraph(
                family_id=g.family_id,
                entities=g.entities,
                count=g.count,
                factor=g.factor,
                endpoint=g.endpoint,
                relation=(tgt, rel, src),
                template_id=g.template_id + ":cf_rel_rev",
            )
            pert.append("relation_direction_reverse")
        if negative_relation:
            # drop relation from observation by rendering without it
            g = CanonicalGraph(
                family_id=g.family_id,
                entities=g.entities,
                count=g.count,
                factor=g.factor,
                endpoint=g.endpoint,
                relation=None,
                template_id=g.template_id + ":no_rel",
            )
            pert.append("relation_removed")
        if empty_force:
            pert.append("empty_legitimate")

        text, obs = render_text(
            g,
            rng=rng,
            style=style,  # type: ignore[arg-type]
            include_distractor=distract,
            invert_order=invert,
            empty_force=empty_force,
        )
        if contaminates_dev(text, dev_fps):
            rejection_log.append(
                {"reason": "dev_contamination", "family_id": g.family_id, "text": text[:120]}
            )
            return None
        th = _sha(text)
        if th in seen_hash:
            rejection_log.append({"reason": "exact_duplicate_text", "family_id": g.family_id})
            return None
        seen_hash.add(th)

        example_id = f"{split}-{g.family_id}-{idx:05d}"
        file_id = f"file-{example_id}"
        try:
            targets = build_targets(
                example_id=example_id,
                file_id=file_id,
                text=text,
                observation=obs,
                graph=g,
            )
        except Exception as exc:  # noqa: BLE001
            rejection_log.append(
                {"reason": f"target_build_failed:{exc}", "family_id": g.family_id}
            )
            return None

        # Validate all targets
        try:
            EvidenceExtractionStage.model_validate(targets["TASK_EVIDENCE"])
            EntityCountStage.model_validate(targets["TASK_ENTITY_COUNT"])
            CandidateRelationStage.model_validate(targets["TASK_EXPLICIT_RELATIONS"])
            MinimalCandidateGraphStage.model_validate(targets["TASK_FACTOR_ENDPOINT"])
        except Exception as exc:  # noqa: BLE001
            rejection_log.append(
                {"reason": f"schema_invalid:{exc}", "family_id": g.family_id}
            )
            return None

        # Candidate-only: no forbidden keys in targets
        blob = json.dumps(targets)
        for bad in (
            "determinability",
            "verdict",
            "n_independent",
            "final_independent_n",
            "RuleResult",
        ):
            if f'"{bad}"' in blob:
                rejection_log.append({"reason": f"forbidden:{bad}", "family_id": g.family_id})
                return None

        task = rng.choice(tasks)
        # Curriculum bias: empty examples prefer evidence / entity
        if empty_force:
            task = rng.choice(["TASK_EVIDENCE", "TASK_ENTITY_COUNT", "TASK_EXPLICIT_RELATIONS"])
        target = targets[task]
        user = {
            "contract_version": "2.0.0",
            "task": task,
            "source_text": text,
            "file_id": file_id,
            "domain_hint": "synthetic_p0_alpha",
            "language": "en",
        }
        record = {
            "record_id": example_id,
            "split": split,
            "task": task,
            "schema_version": SCHEMA_VERSION,
            "source_type": "synthetic_graph_first",
            "family_id": g.family_id,
            "leakage_group": g.family_id,
            "graph_hash": _graph_hash(g),
            "text_sha256": th,
            "seed": seed,
            "renderer_version": RENDERER_VERSION,
            "perturbation_manifest": pert
            + ([f"style:{style}", f"invert:{invert}", f"distract:{distract}"]),
            "training_eligible": split == "train",
            "evaluation_eligible": split in {"train", "validation"},
            "generator_inaccessible": False,
            "synthetic": True,
            "grade": "SYN-G0",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user, ensure_ascii=False, sort_keys=True),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(target, ensure_ascii=False, sort_keys=True),
                },
            ],
            "target": target,
            "source_text": text,
            "all_task_targets": {k: True for k in targets},  # presence only; full targets large
        }
        # Store full targets only for the selected task in assistant; keep compact lineage
        record["target_task"] = task
        return record

    # Fill train
    idx = 0
    attempts = 0
    train_list = list(train_fams)
    while len(train) < n_train and attempts < n_train * 20:
        attempts += 1
        fid = rng.choice(train_list)
        graph = by_id[fid]
        mode = rng.random()
        rec = make_one(
            graph,
            "train",
            idx,
            counterfactual=mode < 0.12,
            empty_force=mode > 0.90 or graph.template_id == "empty_methods",
            negative_relation=0.12 <= mode < 0.20,
        )
        idx += 1
        if rec is not None:
            train.append(rec)

    # Fill val
    idx = 0
    attempts = 0
    val_list = list(val_fams)
    while len(val) < n_val and attempts < n_val * 20:
        attempts += 1
        fid = rng.choice(val_list)
        graph = by_id[fid]
        rec = make_one(
            graph,
            "validation",
            idx,
            counterfactual=rng.random() < 0.1,
            empty_force=rng.random() < 0.08,
        )
        idx += 1
        if rec is not None:
            val.append(rec)

    report = {
        "snapshot": "p0-alpha",
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "seed": seed,
        "renderer_version": RENDERER_VERSION,
        "n_train": len(train),
        "n_validation": len(val),
        "n_families_train": len(train_fams),
        "n_families_validation": len(val_fams),
        "family_ids_train": sorted(train_fams),
        "family_ids_validation": sorted(val_fams),
        "tasks": list(P0_TASKS),
        "rejection_log_count": len(rejection_log),
        "rejection_reasons": _count_reasons(rejection_log),
        "dev_fingerprints": len(dev_fps),
        "experiment_class": "synthetic_pre_adaptation",
        "scientific_validation_status": "NOT_STARTED",
        "training_program_status": "P0_LORA_APPROVED",
    }
    return train + val, report


def _count_reasons(log: Sequence[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in log:
        key = str(item.get("reason", "unknown")).split(":")[0]
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def quality_gate(records: Sequence[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    # schema 100%
    for rec in records:
        task = rec["task"]
        target = rec["target"]
        try:
            if task == "TASK_EVIDENCE":
                EvidenceExtractionStage.model_validate(target)
            elif task == "TASK_ENTITY_COUNT":
                EntityCountStage.model_validate(target)
            elif task == "TASK_EXPLICIT_RELATIONS":
                CandidateRelationStage.model_validate(target)
            elif task == "TASK_FACTOR_ENDPOINT":
                MinimalCandidateGraphStage.model_validate(target)
            else:
                errors.append(f"unknown_task:{task}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"schema:{rec['record_id']}:{exc}")
    # family split
    train_f = {r["family_id"] for r in records if r["split"] == "train"}
    val_f = {r["family_id"] for r in records if r["split"] == "validation"}
    leak = train_f & val_f
    if leak:
        errors.append(f"family_leakage:{sorted(leak)[:5]}")
    # task distribution
    task_counts: dict[str, int] = {}
    for r in records:
        task_counts[r["task"]] = task_counts.get(r["task"], 0) + 1
    # Soglie assolute per snapshot pieno; i test unitari usano n ridotti ma
    # richiedono comunque zero errori di schema/leakage.
    size_ok = report["n_train"] >= 40 and report["n_validation"] >= 10
    production_size_ok = report["n_train"] >= 1500 and report["n_validation"] >= 200
    ok = len(errors) == 0 and size_ok
    return {
        "passed": ok,
        "production_size_ok": production_size_ok,
        "errors": errors[:50],
        "error_count": len(errors),
        "task_counts": task_counts,
        "n_train": report["n_train"],
        "n_validation": report["n_validation"],
    }


def write_snapshot(
    output_dir: Path,
    *,
    n_train: int = 2000,
    n_val: int = 300,
    seed: int = 13,
    dev_cases_path: Path | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records, report = generate_p0_alpha_records(
        n_train=n_train,
        n_val=n_val,
        seed=seed,
        dev_cases_path=dev_cases_path,
    )
    gate = quality_gate(records, report)
    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "validation.jsonl"
    with train_path.open("w", encoding="utf-8") as ht:
        for r in records:
            if r["split"] == "train":
                # compact for training: drop bulky all_task_targets
                row = {k: v for k, v in r.items() if k != "all_task_targets"}
                ht.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with val_path.open("w", encoding="utf-8") as hv:
        for r in records:
            if r["split"] == "validation":
                row = {k: v for k, v in r.items() if k != "all_task_targets"}
                hv.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    # mlx chat-only views
    def write_chat(path: Path, split: str) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for r in records:
                if r["split"] != split:
                    continue
                handle.write(
                    json.dumps(
                        {"messages": r["messages"], "record_id": r["record_id"]},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )

    write_chat(output_dir / "train.chat.jsonl", "train")
    write_chat(output_dir / "validation.chat.jsonl", "validation")

    # empty test placeholder
    (output_dir / "TEST_REAL_PLACEHOLDER.jsonl").write_text(
        "", encoding="utf-8"
    )
    (output_dir / "TEST_REAL_PLACEHOLDER.README.md").write_text(
        "# TEST_REAL placeholder\n\nEmpty and inaccessible. Do not populate from synthetic "
        "or from B4_CONSTRAINED_DEV.\n",
        encoding="utf-8",
    )

    manifest = {
        **report,
        "quality_gate": gate,
        "paths": {
            "train": train_path.name,
            "validation": val_path.name,
            "train_chat": "train.chat.jsonl",
            "validation_chat": "validation.chat.jsonl",
        },
        "checksums": {
            "train_sha256": _sha(train_path.read_text(encoding="utf-8")),
            "validation_sha256": _sha(val_path.read_text(encoding="utf-8")),
        },
        "b4_dev_protection": {
            "benchmark_role": "B4_CONSTRAINED_DEV",
            "training_eligible": False,
            "path": "benchmarks/fewshot_p0/cases.jsonl",
        },
        "label": "synthetic_pre_adaptation_experiment",
        "not": [
            "scientific_validation",
            "external_challenge",
            "pilot_validated",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "DATASET_CARD.md").write_text(
        f"""# Dataset Card — P0-alpha (synthetic pre-adaptation)

**Class:** synthetic pre-adaptation experiment (NOT scientific fine-tuning claim)

## Contents

- Train: {manifest['n_train']} records
- Validation: {manifest['n_validation']} records
- Source: graph-first synthetic (`{RENDERER_VERSION}`)
- Tasks: {', '.join(P0_TASKS)}

## Protection

- B4_CONSTRAINED_DEV (39 cases): training_eligible=false, generator inaccessible
- TEST_REAL_PLACEHOLDER: empty

## Statuses

```yaml
training_program_status: P0_LORA_APPROVED
scientific_validation_status: NOT_STARTED
runtime_qualification_status: PARTIALLY_VERIFIED
```

## Quality gate

passed={gate['passed']} errors={gate['error_count']} task_counts={gate['task_counts']}

## Use

Train LoRA `p0-alpha` only. Evaluate on B4 DEV and this validation split.
Do not use for External Challenge or scientific release claims.
""",
        encoding="utf-8",
    )
    if not gate["passed"]:
        raise RuntimeError(f"quality gate failed: {gate}")
    return manifest


__all__ = [
    "P0_TASKS",
    "RENDERER_VERSION",
    "generate_p0_alpha_records",
    "quality_gate",
    "write_snapshot",
]
