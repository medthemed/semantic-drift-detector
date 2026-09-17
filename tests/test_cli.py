"""CLI exit codes and report formats."""

from __future__ import annotations

import json
from pathlib import Path

from semantic_drift_detector.cli import EXIT_DRIFT, EXIT_OK, EXIT_USAGE, main
from semantic_drift_detector.report import render_json, render_text
from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.diff_scan import analyze_diff


def test_cli_version(capsys):
    code = main(["version"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "semantic-drift-detector" in out


def test_cli_snapshot_writes_dna(clean_tree: Path, capsys):
    code = main(["snapshot", str(clean_tree)])
    assert code == EXIT_OK
    assert (clean_tree / "dna.toml").is_file()
    out = capsys.readouterr().out
    assert "wrote DNA profile" in out


def test_cli_check_clean_tree_exit_0(clean_tree: Path, capsys):
    code = main(["check", str(clean_tree)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "STATUS: OK" in out


def test_cli_check_drifted_tree_exit_1(drifted_tree: Path, capsys):
    code = main(["check", str(drifted_tree)])
    assert code == EXIT_DRIFT
    out = capsys.readouterr().out
    assert "DRIFT DETECTED" in out or "layer" in out.lower()


def test_cli_check_json_output(clean_tree: Path, capsys):
    code = main(["check", str(clean_tree), "--json"])
    assert code in (EXIT_OK, EXIT_DRIFT)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "entropy" in payload
    assert "violations" in payload
    assert "breached" in payload


def test_cli_check_missing_dir_exit_2(tmp_path: Path):
    code = main(["check", str(tmp_path / "missing")])
    assert code == EXIT_USAGE


def test_cli_check_diff_missing_file_exit_2(tmp_path: Path):
    code = main(["check", "--diff", str(tmp_path / "no.diff")])
    assert code == EXIT_USAGE


def test_cli_check_diff_with_dna(drifted_tree: Path, tmp_path: Path, capsys):
    from semantic_drift_detector.profile import extract_dna, save_dna

    dna = extract_dna(drifted_tree)
    dna_path = tmp_path / "dna.toml"
    save_dna(dna, dna_path)

    diff_file = tmp_path / "patch.diff"
    diff_file.write_text(
        """\
diff --git a/src/myapp/domain/order.py b/src/myapp/domain/order.py
--- a/src/myapp/domain/order.py
+++ b/src/myapp/domain/order.py
@@ -0,0 +1,2 @@
+from myapp.adapters.payment import charge
+charge(1.0)
""",
        encoding="utf-8",
    )
    code = main(["check", "--diff", str(diff_file), "--dna", str(dna_path)])
    assert code == EXIT_DRIFT
    out = capsys.readouterr().out
    assert "layer" in out.lower() or "DRIFT" in out


def test_cli_threshold_override(clean_tree: Path, capsys):
    # Clean tree entropy is low but not zero (graph-shape components).
    # Generous threshold → OK; absurdly strict threshold → drift.
    code_ok = main(["check", str(clean_tree), "--threshold", "0.5"])
    assert code_ok == EXIT_OK
    capsys.readouterr()
    code_strict = main(["check", str(clean_tree), "--threshold", "0.0"])
    assert code_strict == EXIT_DRIFT


def test_render_text_and_json_shapes(clean_tree: Path):
    result = analyze_directory(clean_tree)
    text = render_text(result, verbose=True)
    assert "entropy:" in text
    assert "STATUS:" in text
    payload = json.loads(render_json(result))
    assert payload["mode"] == "directory"
    assert isinstance(payload["violations"], list)


def test_cli_snapshot_yaml_format(clean_tree: Path, capsys):
    code = main(["snapshot", str(clean_tree), "--format", "yaml"])
    assert code == EXIT_OK
    assert (clean_tree / "dna.yaml").is_file()
    capsys.readouterr()
