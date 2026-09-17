"""Directory snapshot analysis."""

from __future__ import annotations

from pathlib import Path

from semantic_drift_detector.errors import DirectoryNotFoundError
from semantic_drift_detector.entropy import compute_entropy
from semantic_drift_detector.parser import build_snapshot
from semantic_drift_detector.profile import load_dna_for_root, select_profile
from semantic_drift_detector.rules import evaluate_rules
from semantic_drift_detector.types import CheckResult, DNAProfile, ModuleInfo


def analyze_directory(
    root: str | Path,
    dna_path: str | Path | None = None,
    profile_name: str | None = None,
) -> CheckResult:
    """Analyze a full directory tree against DNA (loaded or inferred).

    Parameters
    ----------
    root:
        Directory to scan.
    dna_path:
        Optional explicit DNA profile file. When omitted, a profile under
        ``root`` is used if present, otherwise rules are inferred.
    profile_name:
        Optional named profile from the DNA file's ``profiles`` section.
        ``None`` or ``"default"`` uses the base rules.

    Returns
    -------
    CheckResult
        Violations, entropy score, and metadata for the scan.

    Raises
    ------
    DirectoryNotFoundError
        If ``root`` does not exist.
    DnaFileNotFoundError / InvalidDnaError
        If ``dna_path`` is provided but cannot be loaded.
    UnknownProfileError
        If ``profile_name`` is not defined in the DNA file.
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise DirectoryNotFoundError(str(root_path))

    if dna_path is not None:
        from semantic_drift_detector.profile import load_dna

        dna = load_dna(dna_path)
        source = str(dna_path)
        rules = select_profile(dna, profile_name)
        modules, edges = build_snapshot(root_path, exclude=list(rules.exclude))
    else:
        dna, source = load_dna_for_root(root_path)
        rules = select_profile(dna, profile_name)
        if rules.exclude or profile_name not in (None, "default"):
            modules, edges = build_snapshot(root_path, exclude=list(rules.exclude))
        else:
            modules, edges = dna.modules, dna.edges

    violations = evaluate_rules(modules, edges, rules, root=root_path)
    entropy = compute_entropy(modules, edges, violations, rules)
    checked = [m.path for m in modules]

    return CheckResult(
        violations=violations,
        entropy=entropy,
        checked_files=checked,
        dna_source=source,
        threshold=rules.entropy_threshold,
        mode="directory",
    )


def analyze_directory_with_profile(
    root: str | Path, dna: DNAProfile
) -> CheckResult:
    root_path = Path(root).resolve()
    modules, edges = build_snapshot(root_path, exclude=list(dna.rules.exclude))
    violations = evaluate_rules(modules, edges, dna.rules, root=root_path)
    entropy = compute_entropy(modules, edges, violations, dna.rules)
    return CheckResult(
        violations=violations,
        entropy=entropy,
        checked_files=[m.path for m in modules],
        dna_source=dna.project_root or "profile",
        threshold=dna.rules.entropy_threshold,
        mode="directory",
    )


def module_count(result: CheckResult) -> int:
    return len(result.checked_files)


__all__ = [
    "analyze_directory",
    "analyze_directory_with_profile",
    "module_count",
]
