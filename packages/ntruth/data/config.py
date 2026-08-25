"""Configuration constants, paths, and environment settings for N-Truth dataset acquisition."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATASET_ROOT = Path("/Volumes/FLASH128/N-Truth-Datasets")
DEFAULT_SEED = "20260803"

SOURCE_DATA_VERSION = "2.0.3"
SOURCE_DATA_HF_REPO = "EMBO/SourceData"

PRECLINIE_VERSION = "f38df55a28505a77d30eefb5b867bbfdcc9baf25"
PRECLINIE_GITHUB_OWNER = "Ineichen-Group"
PRECLINIE_GITHUB_REPO = "Preclinical_IE_Dataset"

MEASEVAL_VERSION = "1fa738b6bc9b72c84c88a80344ca3ab39a310a44"
MEASEVAL_GITHUB_OWNER = "harperco"
MEASEVAL_GITHUB_REPO = "MeasEval"

CRAFT_VERSION = "v5.0.2"
CRAFT_GITHUB_OWNER = "lhunter-lab"
CRAFT_GITHUB_REPO = "CRAFT"

# Universal forbidden targets for public auxiliary datasets in N-Truth
FORBIDDEN_NTRUTH_TARGETS: list[str] = [
    "independent_n",
    "experimental_unit",
    "independently_assigned",
    "allocation_level",
    "application_level",
    "determinability_state",
]

# Task policies per dataset
DATASET_TASK_POLICIES: dict[str, list[str]] = {
    "SourceData": [
        "biomedical_entity_extraction",
        "assay_extraction",
        "experimental_role_tagging",
        "caption_parsing",
    ],
    "PreClinIE": [
        "rigor_indicator_extraction",
        "study_characteristic_extraction",
        "methods_information_extraction",
    ],
    "MeasEval": [
        "quantity_extraction",
        "unit_extraction",
        "measurement_context_extraction",
        "measurement_relation_extraction",
    ],
    "CRAFT": [
        "ontology_concept_extraction",
        "biomedical_coreference",
        "syntactic_auxiliary_training",
    ],
}


def configure_external_cache_environment(root: Path) -> dict[str, str]:
    """Configures explicit environment variables redirecting all cache to external storage."""
    cache_root = root / "cache"
    env_updates = {
        "HF_HOME": str(cache_root / "huggingface"),
        "HF_DATASETS_CACHE": str(cache_root / "huggingface" / "datasets"),
        "HUGGINGFACE_HUB_CACHE": str(cache_root / "huggingface" / "hub"),
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
        "TMPDIR": str(cache_root / "temporary"),
    }
    for key, value in env_updates.items():
        os.environ[key] = value
        Path(value).mkdir(parents=True, exist_ok=True)
    return env_updates


def get_manifests_dir() -> Path:
    """Returns absolute path to package-bundled manifests directory."""
    return Path(__file__).parent / "manifests"
