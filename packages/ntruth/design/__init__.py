"""Design compiler local-first: specifica, elicitazione e handoff neutro."""

from ntruth.design.compiler import compile_design, compile_experiment_block
from ntruth.design.elicit import elicit_design
from ntruth.design.io import (
    design_specification_json_schema,
    dumps_design_compilation,
    dumps_design_specification,
    load_design_specification,
    loads_design_specification,
    write_design_compilation,
    write_design_json_schema,
    write_design_specification,
)
from ntruth.design.schema import (
    DESIGN_SPECIFICATION_VERSION,
    AllocationHandoff,
    AnalysisHandoff,
    ClusterHandoff,
    CompilationStatus,
    DesignCompilation,
    DesignSpecification,
    ElicitationResult,
    EndpointHandoff,
    NestingHandoff,
    RepeatedMeasureHandoff,
    TargetHandoff,
    TargetPopulationSupport,
    UnresolvedAssumption,
)

__all__ = [
    "DESIGN_SPECIFICATION_VERSION",
    "AllocationHandoff",
    "AnalysisHandoff",
    "ClusterHandoff",
    "CompilationStatus",
    "DesignCompilation",
    "DesignSpecification",
    "ElicitationResult",
    "EndpointHandoff",
    "NestingHandoff",
    "RepeatedMeasureHandoff",
    "TargetHandoff",
    "TargetPopulationSupport",
    "UnresolvedAssumption",
    "compile_design",
    "compile_experiment_block",
    "design_specification_json_schema",
    "dumps_design_compilation",
    "dumps_design_specification",
    "elicit_design",
    "load_design_specification",
    "loads_design_specification",
    "write_design_compilation",
    "write_design_json_schema",
    "write_design_specification",
]
