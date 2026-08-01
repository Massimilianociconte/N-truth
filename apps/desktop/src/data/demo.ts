import type { ExperimentBlock, GraphNode, Report, Severity } from "../types";

const provenance = (origin = "explicit") => ({ origin, evidence_ids: [] });

function node(
  id: string,
  type: string,
  label: string,
  count: number | null,
  confidence = 0.86,
): GraphNode {
  return {
    id,
    type,
    label,
    count,
    attributes: {},
    evidence_ids: [`ev-${id}`],
    confidence,
    provenance: provenance(),
  };
}

function block(
  index: number,
  title: string,
  severity: Severity,
  sourceLine: string,
  n: number,
): ExperimentBlock {
  const prefix = `demo-${index}`;
  const nodes = [
    node(`${prefix}-organism`, "Animal", "Animali C57BL/6J", n),
    node(`${prefix}-sample`, "PrimarySample", "Campioni fecali", n * 3),
    node(`${prefix}-treatment`, "Treatment", index === 1 ? "Dieta" : "Antibiotico", 2),
    node(`${prefix}-time`, "FactorLevel", "T0 · 4 · 8 settimane", 3),
    node(`${prefix}-endpoint`, "Endpoint", "16S rRNA (V3–V4)", null),
  ];
  const evidenceId = `ev-${prefix}-main`;
  const factorId = `${prefix}-factor`;
  const contrastId = `${prefix}-contrast`;
  const endpointId = `${prefix}-endpoint-definition`;
  const targetId = `${prefix}-target`;
  const targetStatus = index === 1 ? "user_confirmed" : "extracted";
  return {
    id: prefix,
    title,
    document_id: "demo-document",
    source_file_ids: ["demo-methods"],
    inference_targets:
      index === 3
        ? []
        : [
            {
              id: targetId,
              question_text:
                index === 1
                  ? "La dieta modifica la composizione del microbiota nel tempo?"
                  : "L'antibiotico modifica il recupero longitudinale del microbiota?",
              claim_text:
                index === 1
                  ? "Effetto della dieta negli animali studiati."
                  : "Effetto dell'antibiotico dopo il washout.",
              population_of_inference:
                index === 1 ? "animali C57BL/6J nelle condizioni dichiarate" : "non confermata",
              factor_ids: [factorId],
              contrast_ids: [contrastId],
              endpoint_ids: [endpointId],
              target_biological_unit: "Animal",
              evidence_ids: targetStatus === "extracted" ? [evidenceId] : [],
              status: targetStatus,
            },
          ],
    factors: [
      {
        id: factorId,
        name: index === 1 ? "dieta" : "trattamento antibiotico",
        levels: index === 1 ? ["standard", "fibra"] : ["antibiotico", "veicolo"],
        kind: index === 1 ? "diet" : "treatment",
        assignment_level: "Animal",
        assignment_confidence: 0.88,
        allocation_level: "Animal",
        application_level: "Animal",
        allocation_confidence: 0.88,
        application_confidence: 0.82,
        evidence_ids: [evidenceId],
      },
    ],
    contrasts: [
      {
        id: contrastId,
        label: index === 1 ? "fibra vs standard" : "antibiotico vs veicolo",
        factor_id: factorId,
        group_a: index === 1 ? "fibra" : "antibiotico",
        group_b: index === 1 ? "standard" : "veicolo",
        endpoint_ids: [endpointId],
        evidence_ids: [evidenceId],
      },
    ],
    endpoints: [
      {
        id: endpointId,
        name: "composizione 16S rRNA",
        measured_on: "PrimarySample",
        timepoints: ["T0", "4 settimane", "8 settimane"],
        aggregation: null,
        evidence_ids: [evidenceId],
      },
    ],
    estimands:
      index === 1
        ? [
            {
              id: `${prefix}-estimand`,
              endpoint_id: endpointId,
              effect_measure: "differenza nella composizione del microbiota",
              target_population_or_unit: "animali C57BL/6J nelle condizioni dichiarate",
              generalization_level: "Animal",
              factor_ids: [factorId],
              timepoint: "8 settimane",
              condition: null,
              evidence_ids: [evidenceId],
              provenance: {
                origin: "user",
                evidence_ids: [evidenceId],
                actor_role: "researcher",
              },
            },
          ]
        : [],
    hierarchy: {
      nodes,
      relations: [
        ["sample", "organism", "derived_from"],
        ["organism", "treatment", "assigned_to"],
        ["organism", "time", "repeated_measure_of"],
        ["sample", "endpoint", "measured_on"],
        ["time", "endpoint", "measured_on"],
      ].map(([from, to, type], relationIndex) => ({
        id: `${prefix}-rel-${relationIndex}`,
        type,
        source: `${prefix}-${from}`,
        target: `${prefix}-${to}`,
        attributes: {},
        evidence_ids: [evidenceId],
        confidence: 0.82,
        provenance: provenance("derived"),
      })),
    },
    n_statements: [
      {
        id: `${prefix}-n`,
        value: n,
        entity_type: "animali per gruppo",
        node_type: "Animal",
        raw_text: `n = ${n} per gruppo`,
        evidence_ids: [evidenceId],
        confidence: 0.62,
      },
    ],
    unit_assessments: [],
    alerts: [
      {
        id: `${prefix}-alert-n`,
        rule_id: "GEN-006",
        ruleset_version: "0.1.0",
        severity: "medium",
        alert_class: "inference_scope",
        message: "La numerosità non è esplicitamente collegata a ogni gruppo ed endpoint.",
        confidence: 0.62,
        evidence_ids: [evidenceId],
        missing_information: ["scope di n per gruppo ed endpoint"],
        requires_human_confirmation: true,
      },
      {
        id: `${prefix}-alert-replica`,
        rule_id: "GEN-005",
        ruleset_version: "0.1.0",
        severity,
        alert_class: "design_replication",
        message: "Il materiale non distingue in modo sufficiente repliche tecniche e biologiche.",
        confidence: 0.86,
        evidence_ids: [evidenceId],
        missing_information: ["indipendenza delle sorgenti"],
        requires_human_confirmation: true,
      },
      {
        id: `${prefix}-alert-random`,
        rule_id: "ANI-002",
        ruleset_version: "0.1.0",
        severity: "insufficient",
        alert_class: "analytical_dependence",
        message: "La procedura di randomizzazione non è documentata nel materiale disponibile.",
        confidence: 0.58,
        evidence_ids: [evidenceId],
        missing_information: ["randomizzazione"],
        requires_human_confirmation: true,
      },
    ],
    questions: [
      {
        id: `${prefix}-question`,
        text: "Qual è l’unità assegnata indipendentemente al trattamento?",
        reason: "Livello di intervento non univoco.",
        missing_field: "factor.assignment_level",
        priority: 100,
        decisive: true,
        impact: "Determina l'unita sperimentale e il valore di n indipendente.",
      },
    ],
    contradictions: [],
    evidence: [
      {
        id: evidenceId,
        file_id: "demo-methods",
        section_id: `methods-${index}`,
        section_title: "Metodi",
        start: 418,
        end: 612,
        text: sourceLine,
        parser_version: "0.2.0",
        evidence_type: "AUTHOR_ASSERTION",
        extraction_method: "deterministic_demo",
      },
    ],
    corrections: [],
    versions: {
      schema_version: "0.2.0",
      graph_version: "0.2.0",
      parser_version: "0.2.0",
      ruleset_version: "0.1.0",
    },
  };
}

const blocks = [
  block(
    1,
    "Dieta e microbiota",
    "high",
    "I topi C57BL/6J sono stati assegnati a due gruppi (dieta standard vs dieta ricca in fibra), con n = 6 per gruppo. I campioni fecali sono stati raccolti a T0, 4 e 8 settimane.",
    6,
  ),
  block(
    2,
    "Trattamento antibiotico",
    "medium",
    "Dopo il washout, gli animali hanno ricevuto antibiotico o veicolo. Sono state raccolte misure longitudinali; il numero di unità indipendenti non è riportato.",
    8,
  ),
  block(
    3,
    "Follow-up",
    "insufficient",
    "Il follow-up è stato eseguito otto settimane dopo il trattamento. Le perdite al follow-up non sono attribuite ai singoli endpoint.",
    7,
  ),
];

export const DEMO_REPORT: Report = {
  report_id: "demo-report",
  project_id: "demo-project",
  project_name: "Studio microbioma 2026",
  language: "it",
  domain_transparency: {
    declared_domain: "microbiome",
    normalized_domain: "microbiome",
    validation_status: "out_of_scope",
    ood_assessment: "not_evaluated",
    requires_acknowledgement: true,
    warning: "Dominio non validato: confermare prima dell’export.",
  },
  versions: {
    schema_version: "0.2.0",
    parser_version: "0.2.0",
    graph_version: "0.2.0",
    ruleset_version: "0.1.0",
    ontology_version: "0.1.0-candidate",
  },
  blocks,
  summaries: blocks.map((item) => ({
    block_id: item.id,
    title: item.title,
    max_severity: item.alerts[1]?.severity ?? "insufficient",
    n_alerts: item.alerts.length,
    n_questions: item.questions.length,
    n_unresolved_conflicts: 0,
    assessments_with_independent_n: 0,
    assessments_total: 1,
    abstained: true,
  })),
  design_compilations: Object.fromEntries(
    blocks.map((item, index) => {
      const target = item.inference_targets[0];
      const ready = index === 0;
      const question = target
        ? {
            id: `${item.id}-target-confirmation`,
            text: "Confermi domanda, claim e popolazione di inferenza?",
            reason: "Il target estratto resta candidate finché non è confermato.",
            missing_field: `inference_targets[${target.id}].status`,
          }
        : {
            id: `${item.id}-target-missing`,
            text: "Qual è la domanda scientifica e quale popolazione deve sostenere il claim?",
            reason: "Nessun target inferenziale dichiarato.",
            missing_field: "inference_targets",
          };
      return [
        item.id,
        {
          specification_id: `${item.id}-design`,
          status: ready ? "ready" : "abstained",
          abstained: !ready,
          elicitation: {
            questions: ready ? [] : [question],
            blocking_question_ids: ready ? [] : [question.id],
            complete: ready,
          },
          analysis_handoff: {
            target_population_support: ready
              ? "supported"
              : target
                ? "conditional"
                : "unknown",
            targets: target
              ? [
                  {
                    inference_target_id: target.id,
                    status: target.status,
                    question_text: target.question_text,
                    claim_text: target.claim_text,
                    population_of_inference: target.population_of_inference,
                    target_biological_unit: target.target_biological_unit,
                    target_population_support: ready ? "supported" : "conditional",
                    estimand_ids: ready ? item.estimands.map((estimand) => estimand.id) : [],
                  },
                ]
              : [],
            estimands: ready
              ? item.estimands.map((estimand) => ({
                  estimand_id: estimand.id,
                  endpoint_id: estimand.endpoint_id,
                  effect_measure: estimand.effect_measure,
                  target_population_or_unit: estimand.target_population_or_unit,
                  generalization_level: estimand.generalization_level,
                  factor_ids: estimand.factor_ids,
                  timepoint: estimand.timepoint,
                  condition: estimand.condition,
                  evidence_ids: estimand.evidence_ids,
                }))
              : [],
            unresolved_assumptions: ready
              ? []
              : [
                  {
                    id: `${item.id}-assumption`,
                    code: target ? "target_confirmation" : "inference_targets",
                    message: question.text,
                    blocking: true,
                  },
                ],
            prohibited_outputs: [
              "statistical_test_selection",
              "model_formula",
              "power_analysis",
            ],
          },
        },
      ];
    }),
  ),
  positive_outputs: Object.fromEntries(
    blocks.map((item) => [
      item.id,
      {
        block_id: item.id,
        path_status: "incomplete",
        status_reason: "Demo sintetica: completare le domande decisive prima della revisione.",
        non_certifying: true,
        methods_statement: {
          text: "Bozza non generata: la demo non contiene una valutazione scientifica completa.",
          language: "it",
          evidence_ids: [],
          status: "incomplete",
          non_certifying: true,
          limitations: ["Questa vista dimostra il contratto UI e non valida il disegno."],
        },
        n_table: [],
        driver_checklist: [
          ["DRIVER-1", "Experimental unit", "experimental-unit"],
          ["DRIVER-2", "Risk of bias", "risk-bias"],
          ["DRIVER-3", "Experimental model", "experimental-model"],
          ["DRIVER-4", "Experimental procedures", "experimental-procedures"],
          ["DRIVER-5", "Experimental groups and exclusions", "experimental-groups-and-exclusions"],
          ["DRIVER-6", "Data availability and presentation", "data-availability-and-presentation"],
        ].map(([itemId, title, slug]) => ({
          item_id: itemId,
          title,
          status: "not_assessed" as const,
          note: "Non valutato nella demo sintetica.",
          evidence_ids: [],
          source_url: `https://nc3rs.org.uk/3rs-resources/driver-recommendations/${slug}`,
        })),
        statements: [
          {
            id: `${item.id}-demo-limit`,
            layer: "limitation" as const,
            text: "Dati sintetici dimostrativi, non risultato scientifico.",
            evidence_ids: [],
            source: "demo",
          },
        ],
        candidate_analysis_strategies: [],
        decisive_question_ids: item.questions.filter((question) => question.decisive).map((question) => question.id),
      },
    ]),
  ),
  parser_warnings: [],
  limits: [
    "Dati sintetici dimostrativi: non sono un risultato scientifico.",
    "Il layer ML e la validazione esterna non sono inclusi in questa dimostrazione.",
  ],
  disclaimer:
    "Strumento di supporto: gli output non sostituiscono la revisione biostatistica o di dominio.",
};
