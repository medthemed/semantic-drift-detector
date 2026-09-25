"""Interop tests: --format json|sarif-lite|text and report JSON Schema shape."""

from __future__ import annotations

import json
from pathlib import Path

from semantic_drift_detector.cli import EXIT_DRIFT, EXIT_OK, main
from semantic_drift_detector.report import (
    render_batch,
    render_result,
    render_sarif_lite,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate_required_keys(payload: dict, schema: dict) -> None:
    """Minimal structural check: required top-level keys present with right types."""
    for key in schema.get("required", []):
        assert key in payload, f"missing required key: {key}"
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key not in payload:
            continue
        expected = spec.get("type")
        if expected is None:
            continue
        types = expected if isinstance(expected, list) else [expected]
        if "null" in types and payload[key] is None:
            continue
        type_map = {
            "object": dict,
            "array": list,
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
        }
        ok = any(isinstance(payload[key], type_map[t]) for t in types if t in type_map)
        assert ok, f"{key}: expected {types}, got {type(payload[key])}"


def test_cli_format_text_default(clean_tree: Path, capsys):
    code = main(["check", str(clean_tree)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "STATUS:" in out


def test_cli_format_json(clean_tree: Path, capsys):
    code = main(["check", str(clean_tree), "--format", "json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    schema = _load_schema("report.schema.json")
    _validate_required_keys(payload, schema)
    assert payload["mode"] == "directory"
    assert payload["breached"] is False


def test_cli_json_shorthand(clean_tree: Path, capsys):
    code = main(["check", str(clean_tree), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert "entropy" in payload


def test_cli_format_sarif_lite(drifted_tree: Path, capsys):
    code = main(["check", str(drifted_tree), "--format", "sarif-lite"])
    assert code == EXIT_DRIFT
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "2.1.0"
    assert "runs" in payload
    assert len(payload["runs"]) >= 1
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "semantic-drift-detector"
    assert "results" in run
    assert run["properties"]["breached"] is True


def test_sarif_results_shape(drifted_tree: Path):
    from semantic_drift_detector.analyzer import analyze_directory

    result = analyze_directory(drifted_tree)
    doc = json.loads(render_sarif_lite(result, tool_version="0.4.0"))
    results = doc["runs"][0]["results"]
    assert results, "expected at least one SARIF result"
    for item in results:
        assert "ruleId" in item
        assert item["level"] in {"error", "warning"}
        assert "message" in item and "text" in item["message"]


def test_cli_check_batch_format_json(clean_tree: Path, capsys):
    code = main(["check-batch", str(clean_tree), "--format", "json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    schema = _load_schema("batch-report.schema.json")
    _validate_required_keys(payload, schema)
    assert payload["summary"]["total"] == 1


def test_cli_check_batch_format_sarif(clean_tree: Path, drifted_tree: Path, capsys):
    code = main(["check-batch", str(clean_tree), str(drifted_tree), "--format", "sarif-lite"])
    assert code == EXIT_DRIFT
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "2.1.0"
    assert len(payload["runs"]) == 2
    roots = {run["properties"].get("root") for run in payload["runs"]}
    assert any("clean_app" in str(r) for r in roots)
    assert any("drifted_app" in str(r) for r in roots)


def test_render_result_dispatch(clean_tree: Path):
    from semantic_drift_detector.analyzer import analyze_directory

    result = analyze_directory(clean_tree)
    assert "STATUS" in render_result(result, fmt="text")
    assert json.loads(render_result(result, fmt="json"))["breached"] is False
    assert json.loads(render_result(result, fmt="sarif-lite"))["version"] == "2.1.0"


def test_render_batch_dispatch(clean_tree: Path):
    from semantic_drift_detector.batch import check_batch

    report = check_batch([clean_tree])
    assert "batch report" in render_batch(report, fmt="text")
    assert "summary" in json.loads(render_batch(report, fmt="json"))
    assert "runs" in json.loads(render_batch(report, fmt="sarif-lite"))


def test_report_schema_files_exist():
    assert (SCHEMA_DIR / "report.schema.json").is_file()
    assert (SCHEMA_DIR / "batch-report.schema.json").is_file()
    report_schema = _load_schema("report.schema.json")
    assert report_schema["title"]
    assert "breached" in report_schema["properties"]
