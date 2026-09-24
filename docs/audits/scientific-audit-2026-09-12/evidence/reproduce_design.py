from ntruth.scientific.assignment_anchor import evaluate_contrast_support
from ntruth.scientific.design_matrix import evaluate_design_matrix


def show(name, assignments, levels, blocks):
    x = evaluate_design_matrix(assignments=assignments, declared_levels=levels, blocks=blocks)
    g = x.gate_inputs_for_factor("treatment")
    print(
        name,
        {
            "pairs": x.aliased_factor_pairs,
            "variation": dict(x.within_block_variation),
            "inputs": g,
            "status": evaluate_contrast_support(
                **g, exposure_separable=True, information_sufficient=True
            ).value,
        },
    )


show(
    "unrelated_alias",
    {
        "u1": {"treatment": "C", "batch": "b1", "day": "d1"},
        "u2": {"treatment": "T", "batch": "b1", "day": "d1"},
        "u3": {"treatment": "C", "batch": "b2", "day": "d2"},
        "u4": {"treatment": "T", "batch": "b2", "day": "d2"},
    },
    {"treatment": ["C", "T"], "batch": ["b1", "b2"], "day": ["d1", "d2"]},
    {"u1": "b1", "u2": "b1", "u3": "b2", "u4": "b2"},
)
show(
    "nested_confounding",
    {
        "u1": {"treatment": "C", "batch": "b1"},
        "u2": {"treatment": "C", "batch": "b2"},
        "u3": {"treatment": "T", "batch": "b3"},
        "u4": {"treatment": "T", "batch": "b4"},
    },
    {"treatment": ["C", "T"], "batch": ["b1", "b2", "b3", "b4"]},
    {"u1": "all", "u2": "all", "u3": "all", "u4": "all"},
)
show(
    "missing_as_variation",
    {"u1": {"treatment": "C"}, "u2": {}, "u3": {"treatment": "T"}},
    {"treatment": ["C", "T"]},
    {"u1": "b1", "u2": "b1", "u3": "b2"},
)
show(
    "no_block",
    {"u1": {"treatment": "C"}, "u2": {"treatment": "T"}},
    {"treatment": ["C", "T"]},
    None,
)
show(
    "invented_block",
    {"u1": {"treatment": "C"}, "u2": {"treatment": "T"}},
    {"treatment": ["C", "T"]},
    {"u1": "all", "u2": "all"},
)
