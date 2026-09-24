"""Semantic drift detector: catch architectural entropy before it compounds.

Public API:
    analyze_directory, analyze_diff, check_batch, check_one, compute_entropy,
    evaluate_rules, extract_dna, load_manifest, load_profile, render_json,
    render_text, save_dna, select_profile
"""

from __future__ import annotations

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.batch import (
    BatchItemResult,
    BatchReport,
    check_batch,
    check_one,
    load_manifest,
)
from semantic_drift_detector.diff_scan import analyze_diff
from semantic_drift_detector.entropy import compute_entropy
from semantic_drift_detector.errors import (
    DirectoryNotFoundError,
    DnaFileNotFoundError,
    DnaProfileError,
    InvalidDnaError,
    SemanticDriftError,
    UnknownProfileError,
)
from semantic_drift_detector.profile import (
    extract_dna,
    load_dna,
    load_profile,
    save_dna,
    select_profile,
)
from semantic_drift_detector.report import render_json, render_text
from semantic_drift_detector.rules import evaluate_rules
from semantic_drift_detector.types import (
    CheckResult,
    DNAProfile,
    DNARules,
    EntropyScore,
    Violation,
)

__version__ = "0.4.0"

__all__ = [
    "BatchItemResult",
    "BatchReport",
    "CheckResult",
    "DNAProfile",
    "DNARules",
    "DirectoryNotFoundError",
    "DnaFileNotFoundError",
    "DnaProfileError",
    "EntropyScore",
    "InvalidDnaError",
    "SemanticDriftError",
    "UnknownProfileError",
    "Violation",
    "__version__",
    "analyze_diff",
    "analyze_directory",
    "check_batch",
    "check_one",
    "compute_entropy",
    "evaluate_rules",
    "extract_dna",
    "load_dna",
    "load_manifest",
    "load_profile",
    "render_json",
    "render_text",
    "save_dna",
    "select_profile",
]
