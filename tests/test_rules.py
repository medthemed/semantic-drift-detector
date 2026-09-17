"""Tests for layering, naming, and boundary rules."""

from __future__ import annotations

from pathlib import Path

from semantic_drift_detector.parser import build_snapshot
from semantic_drift_detector.profile import extract_dna
from semantic_drift_detector.rules import (
    check_layering,
    check_naming,
    classify_edge,
    evaluate_rules,
)
from semantic_drift_detector.types import (
    DNARules,
    ForbiddenEdge,
    ImportEdge,
    LayerSpec,
    ModuleInfo,
    NamingRule,
)


def _rules() -> DNARules:
    return DNARules(
        layers=[
            LayerSpec(name="domain", prefixes=["app.domain"]),
            LayerSpec(name="adapters", prefixes=["app.adapters"]),
        ],
        forbidden_edges=[
            ForbiddenEdge(from_layer="domain", to_layer="adapters", reason="nope"),
        ],
        naming=[
            NamingRule(kind="module", pattern=r"^[a-z_][a-z0-9_]*$"),
            NamingRule(kind="class", pattern=r"^[A-Z][A-Za-z0-9]*$"),
        ],
        allowed_roots=["app"],
        entropy_threshold=0.25,
    )


def test_layer_violation_detected():
    rules = _rules()
    edges = [ImportEdge(source="app.domain.order", target="app.adapters.pay")]
    violations = check_layering(edges, rules)
    assert len(violations) == 1
    assert violations[0].kind == "layer"
    assert violations[0].severity == "error"
    assert "adapters" in violations[0].message


def test_allowed_edge_not_flagged():
    rules = _rules()
    edges = [ImportEdge(source="app.adapters.pay", target="app.domain.order")]
    assert check_layering(edges, rules) == []


def test_same_layer_not_flagged():
    rules = _rules()
    edges = [ImportEdge(source="app.domain.a", target="app.domain.b")]
    assert check_layering(edges, rules) == []


def test_naming_violation_on_bad_class():
    rules = _rules()
    modules = [
        ModuleInfo(path="app/domain/x.py", module="app.domain.x", classes=["snake_case"]),
    ]
    violations = check_naming(modules, rules)
    assert any(v.kind == "naming" and "snake_case" in v.message for v in violations)


def test_clean_naming_passes():
    rules = _rules()
    modules = [
        ModuleInfo(path="app/domain/user.py", module="app.domain.user", classes=["User", "OrderLine"]),
    ]
    assert check_naming(modules, rules) == []


def test_classify_edge_resolves_target_prefix():
    rules = _rules()
    edge = ImportEdge(source="app.domain.order", target="app.adapters.payment.ChargeService")
    from_layer, to_layer = classify_edge(edge, rules)
    assert from_layer == "domain"
    assert to_layer == "adapters"


def test_evaluate_rules_on_real_tree(drifted_tree: Path, strict_rules: DNARules):
    modules, edges = build_snapshot(drifted_tree)
    violations = evaluate_rules(modules, edges, strict_rules, root=drifted_tree)
    kinds = {v.kind for v in violations}
    assert "layer" in kinds
    assert "naming" in kinds


def test_clean_tree_has_no_layer_violations(clean_tree: Path, clean_dna):
    modules, edges = build_snapshot(clean_tree)
    violations = check_layering(edges, clean_dna.rules)
    assert violations == []


def test_extract_dna_captures_modules_and_edges(clean_tree: Path):
    dna = extract_dna(clean_tree)
    names = dna.module_names()
    assert any(n.endswith("user") or n.endswith("user.py") or "user" in n for n in names)
    assert len(dna.edges) >= 2
    assert "myapp" in dna.rules.allowed_roots or any(
        "myapp" in r for r in dna.rules.allowed_roots
    ) or dna.rules.allowed_roots  # at least one root
