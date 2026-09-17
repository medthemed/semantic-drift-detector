"""Tests for directory analysis and DNA persistence."""

from __future__ import annotations

from pathlib import Path

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.profile import (
    extract_dna,
    load_dna,
    load_dna_for_root,
    save_dna,
)


def test_clean_tree_passes_with_inferred_dna(clean_tree: Path):
    result = analyze_directory(clean_tree)
    assert result.mode == "directory"
    assert result.entropy is not None
    assert 0.0 <= result.entropy.value <= 1.0
    # Clean layered tree should not produce layer errors
    assert result.errors == []
    assert not result.breached


def test_drifted_tree_reports_layer_errors(drifted_tree: Path, strict_rules):
    dna = extract_dna(drifted_tree, rules=strict_rules)
    result = analyze_directory(drifted_tree, dna_path=None)
    # Without dna file, inference still finds domain→adapters
    layer_errors = [v for v in result.violations if v.kind == "layer"]
    assert layer_errors, f"expected layer errors, got: {result.violations}"


def test_analyze_with_explicit_dna_file(clean_tree: Path, strict_rules, tmp_path: Path):
    dna = extract_dna(clean_tree, rules=strict_rules)
    dna_path = tmp_path / "dna.toml"
    save_dna(dna, dna_path)
    assert dna_path.is_file()

    result = analyze_directory(clean_tree, dna_path=dna_path)
    assert result.dna_source == str(dna_path)
    assert result.errors == []


def test_save_and_load_toml_roundtrip(clean_tree: Path, strict_rules, tmp_path: Path):
    dna = extract_dna(clean_tree, rules=strict_rules)
    path = tmp_path / "dna.toml"
    save_dna(dna, path)
    loaded = load_dna(path)
    assert set(loaded.module_names()) == set(dna.module_names())
    assert loaded.rules.entropy_threshold == dna.rules.entropy_threshold
    assert {layer.name for layer in loaded.rules.layers} == {
        layer.name for layer in dna.rules.layers
    }
    assert loaded.rules.forbidden_edges[0].from_layer == "domain"


def test_save_and_load_yaml_roundtrip(clean_tree: Path, strict_rules, tmp_path: Path):
    dna = extract_dna(clean_tree, rules=strict_rules)
    path = tmp_path / "dna.yaml"
    save_dna(dna, path)
    loaded = load_dna(path)
    assert set(loaded.module_names()) == set(dna.module_names())
    assert loaded.rules.entropy_threshold == dna.rules.entropy_threshold


def test_save_and_load_json_roundtrip(clean_tree: Path, strict_rules, tmp_path: Path):
    dna = extract_dna(clean_tree, rules=strict_rules)
    path = tmp_path / "dna.json"
    save_dna(dna, path)
    loaded = load_dna(path)
    assert set(loaded.module_names()) == set(dna.module_names())


def test_load_dna_for_root_prefers_file(clean_tree: Path, strict_rules):
    dna = extract_dna(clean_tree, rules=strict_rules)
    save_dna(dna, clean_tree / "dna.toml")
    loaded, source = load_dna_for_root(clean_tree)
    assert source.endswith("dna.toml")
    assert set(loaded.module_names()) == set(dna.module_names())


def test_missing_directory_raises(tmp_path: Path):
    missing = tmp_path / "nope"
    try:
        analyze_directory(missing)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
