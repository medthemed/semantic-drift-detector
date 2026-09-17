"""Entropy scoring for architectural drift.

Entropy is a normalized 0–1 score combining:
  - layer violation density (errors / max(1, edges))
  - naming violation density (warnings / max(1, modules))
  - dependency fan-out pressure (avg unique targets per module, capped)
  - unknown/external coupling share (optional, weighted lightly)

Higher means more drift from the captured DNA.
"""

from __future__ import annotations

from collections import defaultdict

from semantic_drift_detector.types import DNARules, EntropyScore, ImportEdge, ModuleInfo, Violation

# Weights must sum to 1.0
WEIGHT_LAYER = 0.45
WEIGHT_NAMING = 0.20
WEIGHT_FANOUT = 0.20
WEIGHT_DENSITY = 0.15

# Fan-out considered "healthy" at or below this many unique outgoing targets
HEALTHY_FANOUT = 8.0


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def layer_component(violations: list[Violation], edge_count: int) -> float:
    """Layer errors scaled by how much of the graph is implicated."""
    layer_errors = sum(1 for v in violations if v.kind == "layer")
    if layer_errors == 0:
        return 0.0
    # Each unique layer error is significant; saturate at 5
    return clamp01(layer_errors / 5.0)


def naming_component(violations: list[Violation], module_count: int) -> float:
    naming_warnings = sum(1 for v in violations if v.kind == "naming")
    if naming_warnings == 0 or module_count == 0:
        return 0.0
    return clamp01(naming_warnings / max(module_count, 1))


def fanout_component(edges: list[ImportEdge], modules: list[ModuleInfo]) -> float:
    """Average unique project targets per module, normalized by HEALTHY_FANOUT."""
    if not modules:
        return 0.0
    targets_by_source: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        targets_by_source[edge.source].add(edge.target)
    if not targets_by_source:
        return 0.0
    avg = sum(len(v) for v in targets_by_source.values()) / len(targets_by_source)
    return clamp01(avg / HEALTHY_FANOUT)


def density_component(edges: list[ImportEdge], modules: list[ModuleInfo]) -> float:
    """Edges-per-module pressure, normalized."""
    if not modules:
        return 0.0
    ratio = len(edges) / max(len(modules), 1)
    # Healthy codebases often sit around 1–3 edges/module; saturate at 10
    return clamp01(ratio / 10.0)


def required_component(violations: list[Violation]) -> float:
    required_errors = sum(1 for v in violations if v.kind == "required")
    return clamp01(required_errors / 3.0)


def compute_entropy(
    modules: list[ModuleInfo],
    edges: list[ImportEdge],
    violations: list[Violation],
    rules: DNARules | None = None,
) -> EntropyScore:
    """Compute a 0–1 entropy score. Always returns a value in [0, 1]."""
    module_count = len(modules)
    edge_count = len(edges)
    error_count = sum(1 for v in violations if v.severity == "error")
    warning_count = sum(1 for v in violations if v.severity == "warning")

    c_layer = layer_component(violations, edge_count)
    c_naming = naming_component(violations, module_count)
    c_fanout = fanout_component(edges, modules)
    c_density = density_component(edges, modules)
    c_required = required_component(violations)

    # Required-pattern failures are treated as hard layer-class entropy
    if c_required > 0:
        c_layer = clamp01(max(c_layer, c_required))

    value = (
        WEIGHT_LAYER * c_layer
        + WEIGHT_NAMING * c_naming
        + WEIGHT_FANOUT * c_fanout
        + WEIGHT_DENSITY * c_density
    )
    value = clamp01(value)

    return EntropyScore(
        value=round(value, 4),
        error_count=error_count,
        warning_count=warning_count,
        edge_count=edge_count,
        module_count=module_count,
        components={
            "layer": round(c_layer, 4),
            "naming": round(c_naming, 4),
            "fanout": round(c_fanout, 4),
            "density": round(c_density, 4),
            "required": round(c_required, 4),
        },
    )


__all__ = [
    "HEALTHY_FANOUT",
    "clamp01",
    "compute_entropy",
    "density_component",
    "fanout_component",
    "layer_component",
    "naming_component",
    "required_component",
]
