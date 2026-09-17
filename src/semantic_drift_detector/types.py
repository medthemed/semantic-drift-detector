"""Core data types for architectural DNA, rules, and check results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportEdge:
    """A directed import from one module/package to another."""

    source: str
    target: str
    line: int | None = None
    file: str | None = None


@dataclass
class LayerSpec:
    """A named architectural layer with membership globs/prefixes."""

    name: str
    packages: list[str] = field(default_factory=list)
    # Optional: explicit package prefixes, e.g. ["myapp.domain"]
    prefixes: list[str] = field(default_factory=list)

    def matches(self, module: str) -> bool:
        mod = module.strip()
        if not mod:
            return False
        for prefix in self.prefixes:
            p = prefix.rstrip(".")
            if mod == p or mod.startswith(p + "."):
                return True
        for pkg in self.packages:
            p = pkg.rstrip(".")
            if mod == p or mod.startswith(p + "."):
                return True
        return False


@dataclass
class ForbiddenEdge:
    """A forbidden dependency from one layer to another."""

    from_layer: str
    to_layer: str
    reason: str = ""

    def key(self) -> tuple[str, str]:
        return (self.from_layer, self.to_layer)


@dataclass
class NamingRule:
    """Regex applied to module basenames or class/function names."""

    kind: str  # "module" | "class" | "function"
    pattern: str
    message: str = ""


@dataclass
class DNARules:
    """Architectural rules captured in dna.toml / dna.yaml."""

    layers: list[LayerSpec] = field(default_factory=list)
    forbidden_edges: list[ForbiddenEdge] = field(default_factory=list)
    naming: list[NamingRule] = field(default_factory=list)
    required_patterns: list[str] = field(default_factory=list)  # path globs that must exist
    allowed_roots: list[str] = field(default_factory=list)  # top-level package roots
    exclude: list[str] = field(default_factory=list)  # path globs to skip during scans
    entropy_threshold: float = 0.25

    def layer_map(self) -> dict[str, LayerSpec]:
        return {layer.name: layer for layer in self.layers}

    def layer_of(self, module: str) -> str | None:
        for layer in self.layers:
            if layer.matches(module):
                return layer.name
        return None


@dataclass
class ModuleInfo:
    """A Python module discovered in a snapshot."""

    path: str  # relative path
    module: str  # dotted module name
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


@dataclass
class DNAProfile:
    """Architectural DNA of a codebase at a point in time."""

    project_root: str = ""
    modules: list[ModuleInfo] = field(default_factory=list)
    rules: DNARules = field(default_factory=DNARules)
    edges: list[ImportEdge] = field(default_factory=list)

    def module_names(self) -> list[str]:
        return [m.module for m in self.modules]

    def edge_pairs(self) -> list[tuple[str, str]]:
        return [(e.source, e.target) for e in self.edges]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "modules": [asdict(m) for m in self.modules],
            "edges": [asdict(e) for e in self.edges],
            "rules": {
                "layers": [asdict(layer) for layer in self.rules.layers],
                "forbidden_edges": [asdict(fe) for fe in self.rules.forbidden_edges],
                "naming": [asdict(nr) for nr in self.rules.naming],
                "required_patterns": list(self.rules.required_patterns),
                "allowed_roots": list(self.rules.allowed_roots),
                "exclude": list(self.rules.exclude),
                "entropy_threshold": self.rules.entropy_threshold,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DNAProfile":
        rules_raw = data.get("rules") or {}
        layers = [
            LayerSpec(
                name=item["name"],
                packages=list(item.get("packages") or []),
                prefixes=list(item.get("prefixes") or []),
            )
            for item in rules_raw.get("layers") or []
        ]
        forbidden = [
            ForbiddenEdge(
                from_layer=item["from_layer"],
                to_layer=item["to_layer"],
                reason=item.get("reason", ""),
            )
            for item in rules_raw.get("forbidden_edges") or []
        ]
        naming = [
            NamingRule(
                kind=item["kind"],
                pattern=item["pattern"],
                message=item.get("message", ""),
            )
            for item in rules_raw.get("naming") or []
        ]
        modules = [
            ModuleInfo(
                path=item["path"],
                module=item["module"],
                imports=list(item.get("imports") or []),
                classes=list(item.get("classes") or []),
                functions=list(item.get("functions") or []),
            )
            for item in data.get("modules") or []
        ]
        edges = [
            ImportEdge(
                source=item["source"],
                target=item["target"],
                line=item.get("line"),
                file=item.get("file"),
            )
            for item in data.get("edges") or []
        ]
        return cls(
            project_root=data.get("project_root", ""),
            modules=modules,
            edges=edges,
            rules=DNARules(
                layers=layers,
                forbidden_edges=forbidden,
                naming=naming,
                required_patterns=list(rules_raw.get("required_patterns") or []),
                allowed_roots=list(rules_raw.get("allowed_roots") or []),
                exclude=list(rules_raw.get("exclude") or []),
                entropy_threshold=float(rules_raw.get("entropy_threshold", 0.25)),
            ),
        )


@dataclass(frozen=True)
class Violation:
    """A single structural or naming violation."""

    kind: str  # "layer" | "naming" | "boundary" | "required" | "unknown_import"
    severity: str  # "error" | "warning"
    message: str
    source: str = ""
    target: str = ""
    file: str | None = None
    line: int | None = None
    rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntropyScore:
    """Entropy of a snapshot or diff, normalized to [0, 1]."""

    value: float
    error_count: int
    warning_count: int
    edge_count: int
    module_count: int
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    """Result of analyzing a directory or diff."""

    violations: list[Violation] = field(default_factory=list)
    entropy: EntropyScore | None = None
    checked_files: list[str] = field(default_factory=list)
    dna_source: str = ""  # path or "inferred"
    threshold: float = 0.25
    mode: str = "directory"  # "directory" | "diff"

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "warning"]

    @property
    def breached(self) -> bool:
        if self.entropy is not None and self.entropy.value > self.threshold:
            return True
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dna_source": self.dna_source,
            "threshold": self.threshold,
            "breached": self.breached,
            "checked_files": list(self.checked_files),
            "violations": [v.to_dict() for v in self.violations],
            "entropy": self.entropy.to_dict() if self.entropy else None,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "total": len(self.violations),
            },
        }
