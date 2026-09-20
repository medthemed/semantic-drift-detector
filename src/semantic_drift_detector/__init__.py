"""Semantic drift detector: catch architectural entropy before it compounds.

Public API:
    analyze_directory, analyze_diff, compute_entropy, evaluate_rules,
    extract_dna, load_profile, render_json, render_text, save_dna
"""

from __future__ import annotations

from semantic_drift_detector.analyzer import analyze_directory
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
from semantic_drift_detector.profile import extract_dna, load_dna, load_profile, save_dna
from semantic_drift_detector.report import render_json, render_text
from semantic_drift_detector.rules import evaluate_rules
from semantic_drift_detector.types import (
    CheckResult,
    DNAProfile,
    DNARules,
    EntropyScore,
    Violation,
)

__version__ = "0.2.0"

__all__ = [
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
    "compute_entropy",
    "evaluate_rules",
    "extract_dna",
    "load_dna",
    "load_profile",
    "render_json",
    "render_text",
    "save_dna",
]
