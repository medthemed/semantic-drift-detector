"""Tests for entropy scoring."""

from __future__ import annotations

from semantic_drift_detector.entropy import (
    clamp01,
    compute_entropy,
    density_component,
    fanout_component,
)
from semantic_drift_detector.types import ImportEdge, ModuleInfo, Violation


def test_clamp01_bounds():
    assert clamp01(-1.0) == 0.0
    assert clamp01(0.0) == 0.0
    assert clamp01(0.5) == 0.5
    assert clamp01(1.0) == 1.0
    assert clamp01(2.0) == 1.0


def test_entropy_low_on_clean_graph():
    modules = [
        ModuleInfo(path="a.py", module="app.a"),
        ModuleInfo(path="b.py", module="app.b"),
    ]
    edges = [ImportEdge(source="app.a", target="app.b")]
    score = compute_entropy(modules, edges, violations=[])
    # No violations → layer/naming components are zero; only mild graph-shape signal
    assert score.components["layer"] == 0.0
    assert score.components["naming"] == 0.0
    assert 0.0 <= score.value < 0.1
    assert score.error_count == 0


def test_entropy_increases_with_layer_errors():
    modules = [ModuleInfo(path="a.py", module="app.domain.a")]
    edges = [ImportEdge(source="app.domain.a", target="app.adapters.x")]
    clean = compute_entropy(modules, edges, violations=[])
    dirty = compute_entropy(
        modules,
        edges,
        violations=[
            Violation(
                kind="layer",
                severity="error",
                message="bad",
                source="app.domain.a",
                target="app.adapters.x",
            )
        ],
    )
    assert dirty.value > clean.value
    assert 0.0 <= dirty.value <= 1.0


def test_entropy_bounds_with_many_violations():
    modules = [ModuleInfo(path=f"m{i}.py", module=f"app.m{i}") for i in range(10)]
    edges = [
        ImportEdge(source=f"app.m{i}", target=f"app.adapters.bad{i}") for i in range(20)
    ]
    violations = [
        Violation(kind="layer", severity="error", message="x", source="s", target="t")
        for _ in range(50)
    ] + [
        Violation(kind="naming", severity="warning", message="y", source="s")
        for _ in range(50)
    ]
    score = compute_entropy(modules, edges, violations)
    assert 0.0 <= score.value <= 1.0
    assert score.value > 0.5


def test_fanout_component_scales():
    modules = [ModuleInfo(path="a.py", module="app.a")]
    few = [ImportEdge(source="app.a", target="app.b")]
    many = [ImportEdge(source="app.a", target=f"app.t{i}") for i in range(12)]
    assert fanout_component(few, modules) < fanout_component(many, modules)
    assert fanout_component(many, modules) <= 1.0


def test_density_component_scales():
    modules = [ModuleInfo(path="a.py", module="app.a")]
    few = [ImportEdge(source="app.a", target="app.b")]
    many = [ImportEdge(source="app.a", target=f"app.t{i}") for i in range(30)]
    assert density_component(few, modules) < density_component(many, modules)


def test_entropy_score_has_components():
    modules = [ModuleInfo(path="a.py", module="app.domain.a")]
    edges = [ImportEdge(source="app.domain.a", target="app.adapters.x")]
    violations = [
        Violation(kind="layer", severity="error", message="bad", source="app.domain.a", target="app.adapters.x")
    ]
    score = compute_entropy(modules, edges, violations)
    assert "layer" in score.components
    assert "fanout" in score.components
    assert score.error_count == 1
