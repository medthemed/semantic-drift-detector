"""Tests for git-diff scanning."""

from __future__ import annotations

from semantic_drift_detector.diff_scan import (
    analyze_diff,
    extract_modules_from_diff,
    parse_diff_files,
)


DIFF_CLEAN = """\
diff --git a/src/myapp/domain/user.py b/src/myapp/domain/user.py
index 111..222 100644
--- a/src/myapp/domain/user.py
+++ b/src/myapp/domain/user.py
@@ -1,3 +1,6 @@
+from dataclasses import dataclass
+
+@dataclass
+class User:
+    id: str
"""


DIFF_DRIFT = """\
diff --git a/src/myapp/domain/order.py b/src/myapp/domain/order.py
index 111..222 100644
--- a/src/myapp/domain/order.py
+++ b/src/myapp/domain/order.py
@@ -0,0 +1,5 @@
+from myapp.adapters.payment import charge
+
+def place_order(amount: float) -> None:
+    charge(amount)
+
diff --git a/src/myapp/domain/BadClass.py b/src/myapp/domain/BadClass.py
index 333..444 100644
--- a/src/myapp/domain/BadClass.py
+++ b/src/myapp/domain/BadClass.py
@@ -0,0 +1,2 @@
+class lower_case:
+    pass
"""


def test_parse_diff_files_extracts_added_lines():
    files = parse_diff_files(DIFF_CLEAN)
    assert "src/myapp/domain/user.py" in files
    added = [line for _, line in files["src/myapp/domain/user.py"]]
    assert any("class User" in line for line in added)


def test_extract_modules_from_diff():
    modules, edges, checked = extract_modules_from_diff(DIFF_CLEAN)
    assert checked == ["src/myapp/domain/user.py"]
    assert modules[0].module == "myapp.domain.user"
    assert "User" in modules[0].classes


def test_diff_layer_violation_detected(drifted_tree, tmp_path):
    # Use explicit rules via a dna file written next to a temp project
    from semantic_drift_detector.profile import extract_dna, save_dna
    from semantic_drift_detector.types import (
        DNARules,
        ForbiddenEdge,
        LayerSpec,
        NamingRule,
    )

    rules = DNARules(
        layers=[
            LayerSpec(name="domain", prefixes=["myapp.domain"]),
            LayerSpec(name="adapters", prefixes=["myapp.adapters"]),
        ],
        forbidden_edges=[
            ForbiddenEdge(from_layer="domain", to_layer="adapters", reason="nope"),
        ],
        naming=[NamingRule(kind="class", pattern=r"^[A-Z][A-Za-z0-9]*$")],
        allowed_roots=["myapp"],
        entropy_threshold=0.25,
    )
    dna = extract_dna(drifted_tree, rules=rules)
    dna_path = tmp_path / "dna.toml"
    save_dna(dna, dna_path)

    result = analyze_diff(DIFF_DRIFT, dna_path=dna_path)
    assert result.mode == "diff"
    kinds = {v.kind for v in result.violations}
    assert "layer" in kinds
    assert result.breached


def test_clean_diff_produces_no_layer_errors(clean_tree, tmp_path):
    from semantic_drift_detector.profile import extract_dna, save_dna

    dna = extract_dna(clean_tree)
    dna_path = tmp_path / "dna.toml"
    save_dna(dna, dna_path)
    result = analyze_diff(DIFF_CLEAN, dna_path=dna_path)
    assert [v for v in result.violations if v.kind == "layer"] == []


def test_non_python_files_ignored():
    text = """\
diff --git a/README.md b/README.md
index 1..2 100644
--- a/README.md
+++ b/README.md
@@ -0,0 +1 @@
+# hello
"""
    modules, edges, checked = extract_modules_from_diff(text)
    assert modules == []
    assert checked == []
