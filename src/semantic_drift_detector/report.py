"""Human-readable and JSON report rendering."""

from __future__ import annotations

import json

from semantic_drift_detector.types import CheckResult, Violation

_SEVERITY_MARK = {"error": "✗", "warning": "!"}


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


__all__ = ["render_json", "render_text", "render_violation"]
