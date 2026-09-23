"""Architectural DNA extraction, load, and save (toml / yaml / json)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from semantic_drift_detector.errors import (
    DnaFileNotFoundError,
    InvalidDnaError,
    UnknownProfileError,
)
from semantic_drift_detector.parser import (
    build_snapshot,
    infer_allowed_roots,
    path_to_module,
    relative_posix,
)
from semantic_drift_detector.types import (
    DNAProfile,
    DNARules,
    ForbiddenEdge,
    LayerSpec,
    NamingRule,
)

DNA_FILENAMES = ("dna.toml", "dna.yaml", "dna.yml", "dna.json")


def find_dna_file(root: Path) -> Path | None:
    for name in DNA_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def extract_dna(root: str | Path, rules: DNARules | None = None) -> DNAProfile:
    """Capture architectural DNA from a directory tree.

    Builds the module dependency graph and, when rules are not supplied,
    infers default layering from common package names (domain/application/
    infrastructure/adapters/interfaces). Paths matching ``rules.exclude``
    globs are skipped.
    """
    root_path = Path(root).resolve()
    exclude = list(rules.exclude) if rules is not None else None
    modules, edges = build_snapshot(root_path, exclude=exclude)
    if rules is None:
        rules = infer_rules(modules)
    elif not rules.allowed_roots:
        rules.allowed_roots = infer_allowed_roots(modules)
    return DNAProfile(
        project_root=str(root_path),
        modules=modules,
        edges=edges,
        rules=rules,
    )


def infer_rules(modules: list) -> DNARules:
    """Infer a sensible default DNA rule set from discovered package structure."""
    allowed_roots = infer_allowed_roots(modules)
    layer_defs = [
        ("domain", ["domain", "core", "entities", "models"]),
        ("application", ["application", "app", "use_cases", "services"]),
        ("infrastructure", ["infrastructure", "infra", "persistence", "db"]),
        ("adapters", ["adapters", "gateway", "gateways", "integrations"]),
        ("interfaces", ["interfaces", "api", "ui", "cli", "presentation", "views"]),
    ]
    layers: list[LayerSpec] = []
    roots = allowed_roots or [""]
    for name, tokens in layer_defs:
        prefixes: list[str] = []
        packages: list[str] = []
        for token in tokens:
            packages.append(token)
            for root_name in roots:
                if root_name:
                    prefixes.append(f"{root_name}.{token}")
        if packages or prefixes:
            layers.append(LayerSpec(name=name, packages=packages, prefixes=prefixes))

    forbidden = [
        ForbiddenEdge(
            from_layer="domain",
            to_layer="infrastructure",
            reason="domain must not depend on infrastructure",
        ),
        ForbiddenEdge(
            from_layer="domain",
            to_layer="adapters",
            reason="domain must not depend on adapters",
        ),
        ForbiddenEdge(
            from_layer="domain",
            to_layer="interfaces",
            reason="domain must not depend on delivery mechanisms",
        ),
        ForbiddenEdge(
            from_layer="application",
            to_layer="adapters",
            reason="application must not depend on adapters",
        ),
        ForbiddenEdge(
            from_layer="application",
            to_layer="interfaces",
            reason="application must not depend on interfaces",
        ),
    ]

    naming = [
        NamingRule(
            kind="module",
            pattern=r"^[a-z_][a-z0-9_]*$",
            message="module names must be snake_case",
        ),
        NamingRule(
            kind="class",
            pattern=r"^[A-Z][A-Za-z0-9]*$",
            message="class names must be PascalCase",
        ),
    ]

    required: list[str] = []
    seen = {m.module for m in modules}
    for token in ("domain", "adapters"):
        if any(token in name.split(".") for name in seen):
            required.append(f"**/{token}/**")

    return DNARules(
        layers=layers,
        forbidden_edges=forbidden,
        naming=naming,
        required_patterns=required,
        allowed_roots=allowed_roots,
        entropy_threshold=0.25,
    )


def load_dna(path: str | Path) -> DNAProfile:
    """Load DNA profile from dna.toml / dna.yaml / dna.json.

    Raises
    ------
    DnaFileNotFoundError
        If ``path`` does not exist.
    InvalidDnaError
        If the file content is not a valid DNA mapping.
    """
    p = Path(path)
    if not p.is_file():
        raise DnaFileNotFoundError(str(p))
    text = p.read_text(encoding="utf-8")
    try:
        data = parse_dna_text(text, p.suffix.lower())
        return DNAProfile.from_dict(data)
    except InvalidDnaError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidDnaError(f"invalid DNA profile {p}: {exc}") from exc


def load_profile(path: str | Path) -> DNAProfile:
    """Load a DNA profile from a file path.

    Stable public API name for :func:`load_dna`. Prefer this in new code.
    """
    return load_dna(path)


def merge_profile_overrides(base: DNARules, overrides: dict[str, Any]) -> DNARules:
    """Apply named-profile overrides onto base rules.

    Scalar keys replace the base value. List keys (layers, forbidden_edges,
    naming, required_patterns, allowed_roots, exclude) replace the list when
    present; omitted keys inherit from base.
    """
    layers = base.layers
    if "layers" in overrides:
        layers = [
            LayerSpec(
                name=item["name"],
                packages=list(item.get("packages") or []),
                prefixes=list(item.get("prefixes") or []),
            )
            for item in overrides["layers"] or []
        ]
    forbidden = base.forbidden_edges
    if "forbidden_edges" in overrides:
        forbidden = [
            ForbiddenEdge(
                from_layer=item["from_layer"],
                to_layer=item["to_layer"],
                reason=item.get("reason", ""),
            )
            for item in overrides["forbidden_edges"] or []
        ]
    naming = base.naming
    if "naming" in overrides:
        naming = [
            NamingRule(
                kind=item["kind"],
                pattern=item["pattern"],
                message=item.get("message", ""),
            )
            for item in overrides["naming"] or []
        ]
    return DNARules(
        layers=layers,
        forbidden_edges=forbidden,
        naming=naming,
        required_patterns=list(
            overrides["required_patterns"]
            if "required_patterns" in overrides
            else base.required_patterns
        ),
        allowed_roots=list(
            overrides["allowed_roots"]
            if "allowed_roots" in overrides
            else base.allowed_roots
        ),
        exclude=list(overrides["exclude"] if "exclude" in overrides else base.exclude),
        entropy_threshold=float(
            overrides.get("entropy_threshold", base.entropy_threshold)
        ),
    )


def select_profile(profile: DNAProfile, name: str | None = None) -> DNARules:
    """Return rules for a named profile, or the base rules when name is None/"default".

    Raises
    ------
    UnknownProfileError
        If ``name`` is not defined in the DNA file's profiles section.
    """
    if name is None or name == "default":
        return profile.rules
    if name not in profile.profiles:
        raise UnknownProfileError(name, available=profile.profile_names())
    return merge_profile_overrides(profile.rules, profile.profiles[name])


def load_dna_for_root(root: str | Path) -> tuple[DNAProfile, str]:
    """Load DNA from root if present; otherwise infer. Returns (profile, source)."""
    root_path = Path(root).resolve()
    dna_file = find_dna_file(root_path)
    if dna_file is not None:
        return load_dna(dna_file), str(dna_file)
    return extract_dna(root_path), "inferred"


def save_dna(profile: DNAProfile, path: str | Path) -> Path:
    """Write DNA profile to path. Format chosen by extension (.toml default)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = profile.to_dict()
    suffix = p.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        p.write_text(dump_yaml(data), encoding="utf-8")
    elif suffix == ".json":
        p.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    else:
        p.write_text(dump_toml(data), encoding="utf-8")
    return p


def parse_dna_text(text: str, suffix: str) -> dict:
    if suffix in {".yaml", ".yml"}:
        return normalize_dna_dict(minimal_yaml_load(text))
    if suffix == ".json":
        return normalize_dna_dict(json.loads(text))
    return normalize_dna_dict(parse_toml(text))


def parse_toml(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - py<3.11
        import tomli as tomllib  # type: ignore

    return tomllib.loads(text)


def normalize_dna_dict(raw: dict) -> dict:
    """Accept either flat DNA dict or nested {dna: {...}} wrapper."""
    if not isinstance(raw, dict):
        raise InvalidDnaError("DNA file must contain a mapping")
    if "dna" in raw and isinstance(raw["dna"], dict):
        return raw["dna"]
    if "rules" in raw or "modules" in raw or "layers" in raw:
        if "rules" not in raw and "layers" in raw:
            rules_keys = {
                "layers",
                "forbidden_edges",
                "naming",
                "required_patterns",
                "allowed_roots",
                "exclude",
                "entropy_threshold",
            }
            rules = {k: raw[k] for k in rules_keys if k in raw}
            rest = {k: v for k, v in raw.items() if k not in rules_keys}
            rest["rules"] = rules
            return rest
        return raw
    return {"rules": raw}


# ---------------------------------------------------------------------------
# TOML writer (stdlib has no writer; emit a stable subset)
# ---------------------------------------------------------------------------

def toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return toml_str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value)!r}")


def dump_toml(data: dict) -> str:
    lines: list[str] = []
    lines.append("# Architectural DNA profile")
    lines.append("# Generated by semantic-drift-detector")
    lines.append("")
    if data.get("project_root"):
        lines.append(f"project_root = {toml_str(str(data['project_root']))}")
        lines.append("")

    rules = data.get("rules") or {}
    lines.append("[rules]")
    lines.append(f"entropy_threshold = {rules.get('entropy_threshold', 0.25)}")
    if rules.get("allowed_roots"):
        lines.append("allowed_roots = " + toml_value([str(x) for x in rules["allowed_roots"]]))
    if rules.get("required_patterns"):
        lines.append(
            "required_patterns = " + toml_value([str(x) for x in rules["required_patterns"]])
        )
    if rules.get("exclude"):
        lines.append("exclude = " + toml_value([str(x) for x in rules["exclude"]]))
    lines.append("")

    for layer in rules.get("layers") or []:
        lines.append("[[rules.layers]]")
        lines.append(f"name = {toml_str(layer['name'])}")
        if layer.get("packages"):
            lines.append("packages = " + toml_value(layer["packages"]))
        if layer.get("prefixes"):
            lines.append("prefixes = " + toml_value(layer["prefixes"]))
        lines.append("")

    for edge in rules.get("forbidden_edges") or []:
        lines.append("[[rules.forbidden_edges]]")
        lines.append(f"from_layer = {toml_str(edge['from_layer'])}")
        lines.append(f"to_layer = {toml_str(edge['to_layer'])}")
        if edge.get("reason"):
            lines.append(f"reason = {toml_str(edge['reason'])}")
        lines.append("")

    for rule in rules.get("naming") or []:
        lines.append("[[rules.naming]]")
        lines.append(f"kind = {toml_str(rule['kind'])}")
        lines.append(f"pattern = {toml_str(rule['pattern'])}")
        if rule.get("message"):
            lines.append(f"message = {toml_str(rule['message'])}")
        lines.append("")

    profiles = data.get("profiles") or {}
    for name in sorted(profiles):
        overrides = profiles[name] or {}
        lines.append(f"[profiles.{name}]")
        if "entropy_threshold" in overrides:
            lines.append(f"entropy_threshold = {overrides['entropy_threshold']}")
        if "allowed_roots" in overrides:
            lines.append(
                "allowed_roots = " + toml_value([str(x) for x in overrides["allowed_roots"]])
            )
        if "required_patterns" in overrides:
            lines.append(
                "required_patterns = "
                + toml_value([str(x) for x in overrides["required_patterns"]])
            )
        if "exclude" in overrides:
            lines.append("exclude = " + toml_value([str(x) for x in overrides["exclude"]]))
        lines.append("")

    for mod in data.get("modules") or []:
        lines.append("[[modules]]")
        lines.append(f"path = {toml_str(mod['path'])}")
        lines.append(f"module = {toml_str(mod['module'])}")
        if mod.get("imports"):
            lines.append("imports = " + toml_value(mod["imports"]))
        if mod.get("classes"):
            lines.append("classes = " + toml_value(mod["classes"]))
        if mod.get("functions"):
            lines.append("functions = " + toml_value(mod["functions"]))
        lines.append("")

    for edge in data.get("edges") or []:
        lines.append("[[edges]]")
        lines.append(f"source = {toml_str(edge['source'])}")
        lines.append(f"target = {toml_str(edge['target'])}")
        if edge.get("file"):
            lines.append(f"file = {toml_str(edge['file'])}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Minimal YAML writer/loader (documented subset)
# ---------------------------------------------------------------------------

def yaml_str(value: str) -> str:
    if value == "" or re.search(r'[:#\[\]{}",\'\n]|^\s|\s$', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def dump_yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return yaml_str(value)
    raise TypeError(f"Unsupported YAML scalar: {type(value)!r}")


def dump_yaml(data: dict, indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(dump_yaml(value, indent + 1))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{pad}{key}: []")
            elif all(not isinstance(v, (dict, list)) for v in value):
                lines.append(f"{pad}{key}:")
                for item in value:
                    lines.append(f"{pad}  - {dump_yaml_scalar(item)}")
            else:
                lines.append(f"{pad}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{pad}  -")
                        lines.append(dump_yaml(item, indent + 2))
                    else:
                        lines.append(f"{pad}  - {dump_yaml_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {dump_yaml_scalar(value)}")
    return "\n".join(lines)


def parse_yaml_scalar(token: str):
    token = token.strip()
    if token == "[]":
        return []
    if token == "{}":
        return {}
    if token in {"true", "True"}:
        return True
    if token in {"false", "False"}:
        return False
    if token in {"null", "Null", "~"}:
        return None
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        inner = token[1:-1]
        if token.startswith('"'):
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    try:
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)
    except ValueError:
        return token


def minimal_yaml_load(text: str) -> dict:
    """Parse the YAML subset emitted by dump_yaml (indent-based maps/lists)."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append(raw.rstrip())

    def parse_block(idx: int, indent: int) -> tuple[dict | list, int]:
        if idx >= len(lines):
            return {}, idx
        first = lines[idx]
        first_indent = len(first) - len(first.lstrip(" "))
        if first_indent < indent:
            return {}, idx
        stripped = first.strip()
        if stripped.startswith("- ") or stripped == "-":
            items: list = []
            while idx < len(lines):
                line = lines[idx]
                cur_indent = len(line) - len(line.lstrip(" "))
                if cur_indent < indent:
                    break
                s = line.strip()
                if not s.startswith("-"):
                    break
                content = s[1:].strip()
                item_indent = cur_indent + 2
                if not content:
                    child, idx = parse_block(idx + 1, item_indent)
                    items.append(child)
                    continue
                if ":" in content and not content.startswith(('"', "'")):
                    key, _, rest = content.partition(":")
                    key = key.strip()
                    rest = rest.strip()
                    item: dict = {}
                    if rest:
                        item[key] = parse_yaml_scalar(rest)
                        child, idx = parse_block(idx + 1, item_indent)
                        if isinstance(child, dict):
                            item.update(child)
                    else:
                        child, idx = parse_block(idx + 1, item_indent)
                        item[key] = child
                    items.append(item)
                else:
                    items.append(parse_yaml_scalar(content))
                    idx += 1
            return items, idx

        result: dict = {}
        while idx < len(lines):
            line = lines[idx]
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent < indent:
                break
            if cur_indent > indent:
                idx += 1
                continue
            s = line.strip()
            if ":" not in s:
                idx += 1
                continue
            key, _, rest = s.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest:
                result[key] = parse_yaml_scalar(rest)
                idx += 1
            else:
                idx += 1
                child, idx = parse_block(idx, indent + 2)
                result[key] = child
        return result, idx

    parsed, _ = parse_block(0, 0)
    if isinstance(parsed, list):
        return {"items": parsed}
    return parsed


def snapshot_path_default(root: Path) -> Path:
    return Path(root) / "dna.toml"


__all__ = [
    "DNA_FILENAMES",
    "dump_toml",
    "dump_yaml",
    "extract_dna",
    "find_dna_file",
    "infer_rules",
    "load_dna",
    "load_dna_for_root",
    "load_profile",
    "merge_profile_overrides",
    "minimal_yaml_load",
    "normalize_dna_dict",
    "parse_dna_text",
    "parse_toml",
    "path_to_module",
    "relative_posix",
    "save_dna",
    "select_profile",
    "snapshot_path_default",
]
