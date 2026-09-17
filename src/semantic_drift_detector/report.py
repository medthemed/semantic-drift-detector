"""Human-readable, JSON, and SARIF-lite report rendering."""

from __future__ import annotations

import json
from typing import Any

from semantic_drift_detector.batch import BatchReport
from semantic_drift_detector.types import CheckResult, Violation

_SEVERITY_MARK = {"error": "✗", "warning": "!"}
SARIF_LEVEL = {"error": "error", "warning": "warning"}
FORMAT_CHOICES = ("text", "json", "sarif-lite")


def render_violation(v: Violation) -> str:
    mark = _SEVERITY_MARK.get(v.severity, "?")
    location = ""
    if v.file:
        location = f" [{v.file}"
        if v.line is not None:
            location += f":{v.line}"
        location += "]"
    return f"  {mark} ({v.severity}) {v.message}{location}"


def render_text(result: CheckResult, verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append("semantic-drift-detector report")
    lines.append("=" * 40)
    lines.append(f"mode:         {result.mode}")
    lines.append(f"dna:          {result.dna_source}")
    lines.append(f"files:        {len(result.checked_files)}")
    lines.append(f"threshold:    {result.threshold}")

    if result.entropy is not None:
        e = result.entropy
        bar = _bar(e.value)
        lines.append(f"entropy:      {e.value:.4f} {bar}")
        if verbose and e.components:
            parts = ", ".join(f"{k}={v:.3f}" for k, v in e.components.items())
            lines.append(f"components:   {parts}")
        lines.append(f"errors:       {e.error_count}")
        lines.append(f"warnings:     {e.warning_count}")

    lines.append("")
    if result.violations:
        lines.append(f"violations ({len(result.violations)}):")
        # errors first, then warnings
        ordered = sorted(result.violations, key=lambda v: (v.severity != "error", v.kind, v.message))
        for v in ordered:
            lines.append(render_violation(v))
    else:
        lines.append("violations:   none")

    lines.append("")
    if result.breached:
        lines.append("STATUS: DRIFT DETECTED (exit 1)")
    else:
        lines.append("STATUS: OK (exit 0)")
    return "\n".join(lines) + "\n"


def _bar(value: float, width: int = 20) -> str:
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def render_json(result: CheckResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent, sort_keys=False) + "\n"


def render_batch_text(report: BatchReport) -> str:
    lines: list[str] = []
    lines.append("semantic-drift-detector batch report")
    lines.append("=" * 40)
    lines.append(f"roots:      {len(report.items)}")
    lines.append(f"ok:         {report.ok_count}")
    lines.append(f"breached:   {report.breached_count}")
    lines.append(f"errors:     {report.error_count}")
    lines.append("")
    for item in report.items:
        if not item.ok:
            lines.append(f"  ERROR  {item.root}: {item.error}")
        elif item.breached:
            entropy = item.result.entropy.value if item.result and item.result.entropy else None
            detail = f" entropy={entropy:.4f}" if entropy is not None else ""
            lines.append(f"  DRIFT  {item.root}{detail}")
        else:
            entropy = item.result.entropy.value if item.result and item.result.entropy else None
            detail = f" entropy={entropy:.4f}" if entropy is not None else ""
            lines.append(f"  OK     {item.root}{detail}")
    lines.append("")
    if report.any_error:
        lines.append("STATUS: ERRORS (exit 2)")
    elif report.any_breached:
        lines.append("STATUS: DRIFT DETECTED (exit 1)")
    else:
        lines.append("STATUS: OK (exit 0)")
    return "\n".join(lines) + "\n"


def render_batch_json(report: BatchReport, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, sort_keys=False) + "\n"


def _sarif_result(v: Violation) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": v.kind,
        "level": SARIF_LEVEL.get(v.severity, "warning"),
        "message": {"text": v.message},
    }
    if v.file:
        loc: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {"uri": v.file.replace("\\", "/")},
            }
        }
        if v.line is not None:
            loc["physicalLocation"]["region"] = {"startLine": v.line}
        result["locations"] = [loc]
    if v.rule:
        result["ruleId"] = v.rule
    return result


def render_sarif_lite(result: CheckResult, tool_version: str = "") -> str:
    """Emit a SARIF 2.1.0-lite document suitable for GitHub code scanning demos.

    Intentionally minimal: one run, one tool, one result per violation.
    Entropy and threshold are carried in ``properties``.
    """
    payload: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "semantic-drift-detector",
                        "informationUri": "https://github.com/medthemed/semantic-drift-detector",
                        "version": tool_version,
                        "rules": [],
                    }
                },
                "results": [_sarif_result(v) for v in result.violations],
                "properties": {
                    "mode": result.mode,
                    "dna_source": result.dna_source,
                    "threshold": result.threshold,
                    "breached": result.breached,
                    "entropy": result.entropy.to_dict() if result.entropy else None,
                    "checked_files": list(result.checked_files),
                },
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def render_batch_sarif_lite(report: BatchReport, tool_version: str = "") -> str:
    """One SARIF run per batch root; empty results for load errors."""
    runs: list[dict[str, Any]] = []
    for item in report.items:
        if item.result is not None:
            doc = json.loads(render_sarif_lite(item.result, tool_version=tool_version))
            run = doc["runs"][0]
            run["properties"]["root"] = item.root
            runs.append(run)
        else:
            runs.append(
                {
                    "tool": {
                        "driver": {
                            "name": "semantic-drift-detector",
                            "informationUri": "https://github.com/medthemed/semantic-drift-detector",
                            "version": tool_version,
                        }
                    },
                    "results": [
                        {
                            "ruleId": "batch-error",
                            "level": "error",
                            "message": {"text": item.error or "unknown error"},
                        }
                    ],
                    "properties": {"root": item.root, "error_type": item.error_type},
                }
            )
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": runs,
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def render_result(result: CheckResult, fmt: str = "text", verbose: bool = False) -> str:
    """Dispatch a single CheckResult to the requested output format."""
    if fmt == "json":
        return render_json(result)
    if fmt == "sarif-lite":
        return render_sarif_lite(result)
    return render_text(result, verbose=verbose)


def render_batch(report: BatchReport, fmt: str = "text") -> str:
    """Dispatch a BatchReport to the requested output format."""
    if fmt == "json":
        return render_batch_json(report)
    if fmt == "sarif-lite":
        return render_batch_sarif_lite(report)
    return render_batch_text(report)


__all__ = [
    "FORMAT_CHOICES",
    "render_batch",
    "render_batch_json",
    "render_batch_sarif_lite",
    "render_batch_text",
    "render_json",
    "render_result",
    "render_sarif_lite",
    "render_text",
    "render_violation",
]
