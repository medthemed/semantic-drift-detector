"""Scan a unified git diff for structural violations against DNA."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from semantic_drift_detector.entropy import compute_entropy
from semantic_drift_detector.parser import (
    extract_definitions,
    extract_imports,
    path_to_module,
)
from semantic_drift_detector.profile import load_dna_for_root
from semantic_drift_detector.rules import evaluate_rules
from semantic_drift_detector.types import (
    CheckResult,
    DNAProfile,
    ImportEdge,
    ModuleInfo,
    Violation,
)

# file header: +++ b/path/to/file.py  or  +++ path/to/file.py
_FILE_HEADER = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_diff_files(diff_text: str) -> dict[str, list[tuple[int, str]]]:
    """Parse a unified diff into {path: [(new_line_no, added_line), ...]}."""
    files: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    new_line = 0

    for raw in diff_text.splitlines():
        header = _FILE_HEADER.match(raw)
        if header:
            current = header.group(1).strip()
            if current == "/dev/null":
                current = None
            else:
                files.setdefault(current, [])
            continue
        if current is None:
            continue
        hunk = _HUNK.match(raw)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            files[current].append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue  # removed line — does not advance new file line counter
        elif raw.startswith("\\"):
            continue
        else:
            # context line
            new_line += 1
    return files


def _reconstruct_added_source(added_lines: list[tuple[int, str]]) -> str:
    return "\n".join(line for _, line in added_lines) + ("\n" if added_lines else "")


def extract_modules_from_diff(diff_text: str) -> tuple[list[ModuleInfo], list[ImportEdge], list[str]]:
    """Build ModuleInfo / ImportEdge lists from added (+) lines in a diff."""
    files = parse_diff_files(diff_text)
    modules: list[ModuleInfo] = []
    edges: list[ImportEdge] = []
    checked: list[str] = []

    for path, added in sorted(files.items()):
        if not path.endswith(".py"):
            continue
        checked.append(path)
        module = path_to_module(path)
        source = _reconstruct_added_source(added)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Partial snippet may not parse; fall back to regex import scan
            imports = _regex_imports(source)
            modules.append(ModuleInfo(path=path, module=module, imports=imports))
            for imp in imports:
                edges.append(ImportEdge(source=module, target=imp, file=path))
            continue

        imports = extract_imports(tree, module)
        classes, functions = extract_definitions(tree)
        modules.append(
            ModuleInfo(
                path=path,
                module=module,
                imports=imports,
                classes=classes,
                functions=functions,
            )
        )
        for imp in imports:
            edges.append(ImportEdge(source=module, target=imp, file=path))
    return modules, edges, checked


def _regex_imports(source: str) -> list[str]:
    """Fallback import extraction when snippet does not parse as full module."""
    imports: list[str] = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("import "):
            rest = s[len("import ") :]
            for part in rest.split(","):
                name = part.strip().split(" as ")[0].strip()
                if name:
                    imports.append(name)
        elif s.startswith("from "):
            m = re.match(r"from\s+([.\w]+)\s+import\s+(.+)", s)
            if not m:
                continue
            mod = m.group(1)
            names = [n.strip().split(" as ")[0].strip() for n in m.group(2).split(",")]
            if mod.startswith("."):
                # relative — keep as-is with dots for layer matching best-effort
                target_base = mod.lstrip(".")
                if target_base:
                    imports.append(target_base)
                continue
            if names and names[0] != "*":
                imports.append(f"{mod}.{names[0]}")
            else:
                imports.append(mod)
    seen: set[str] = set()
    out: list[str] = []
    for item in imports:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def analyze_diff(diff_text: str, dna_path: str | Path | None = None) -> CheckResult:
    """Analyze a git diff against DNA. Uses dna_path if given, else infers from cwd tree."""
    modules, edges, checked = extract_modules_from_diff(diff_text)

    if dna_path is not None:
        from semantic_drift_detector.profile import load_dna

        dna = load_dna(dna_path)
        source = str(dna_path)
    else:
        dna, source = load_dna_for_root(Path.cwd())

    # Prefer DNA layers/rules; analyze only what the diff introduced
    violations = evaluate_rules(modules, edges, dna.rules, root=None)
    # Filter naming noise: only check modules that appear in the diff
    entropy = compute_entropy(modules, edges, violations, dna.rules)

    return CheckResult(
        violations=violations,
        entropy=entropy,
        checked_files=checked,
        dna_source=source,
        threshold=dna.rules.entropy_threshold,
        mode="diff",
    )


def analyze_diff_with_profile(diff_text: str, dna: DNAProfile) -> CheckResult:
    modules, edges, checked = extract_modules_from_diff(diff_text)
    violations = evaluate_rules(modules, edges, dna.rules, root=None)
    entropy = compute_entropy(modules, edges, violations, dna.rules)
    return CheckResult(
        violations=violations,
        entropy=entropy,
        checked_files=checked,
        dna_source=dna.project_root or "profile",
        threshold=dna.rules.entropy_threshold,
        mode="diff",
    )


__all__ = [
    "analyze_diff",
    "analyze_diff_with_profile",
    "extract_modules_from_diff",
    "parse_diff_files",
]
