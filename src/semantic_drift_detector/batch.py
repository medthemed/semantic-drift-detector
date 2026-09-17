"""Batch directory checks across many project roots.

Pure-core note
--------------
``check_one`` and ``check_batch`` only read the filesystem through
``analyze_directory`` and never mutate shared global state. Each call is
independent given its ``(root, dna_path, profile_name)`` arguments, so
callers may map roots across a ``ThreadPoolExecutor`` or
``ProcessPoolExecutor`` without locks. The sequential loop here is the
reference implementation; swap in a pool when wall-clock time matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.errors import SemanticDriftError
from semantic_drift_detector.types import CheckResult


@dataclass
class BatchItemResult:
    """Outcome for a single root in a batch run."""

    root: str
    ok: bool
    error: str | None = None
    error_type: str | None = None
    result: CheckResult | None = None

    @property
    def breached(self) -> bool:
        return bool(self.result is not None and self.result.breached)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "ok": self.ok,
            "error": self.error,
            "error_type": self.error_type,
            "breached": self.breached,
            "result": self.result.to_dict() if self.result is not None else None,
        }


@dataclass
class BatchReport:
    """Aggregated results for a batch of roots."""

    items: list[BatchItemResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.items if item.ok and not item.breached)

    @property
    def breached_count(self) -> int:
        return sum(1 for item in self.items if item.breached)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if not item.ok)

    @property
    def any_breached(self) -> bool:
        return self.breached_count > 0

    @property
    def any_error(self) -> bool:
        return self.error_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": len(self.items),
                "ok": self.ok_count,
                "breached": self.breached_count,
                "errors": self.error_count,
            },
            "items": [item.to_dict() for item in self.items],
        }


def load_manifest(path: str | Path) -> list[str]:
    """Read project roots from a manifest file.

    One path per line. Blank lines and ``#`` comments are ignored.
    Relative paths are resolved against the manifest's directory.
    """
    manifest = Path(path)
    if not manifest.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest}")
    base = manifest.resolve().parent
    roots: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        candidate = Path(line)
        if not candidate.is_absolute():
            candidate = (base / candidate).resolve()
        else:
            candidate = candidate.resolve()
        roots.append(str(candidate))
    return roots


def check_one(
    root: str | Path,
    dna_path: str | Path | None = None,
    profile_name: str | None = None,
) -> BatchItemResult:
    """Analyze a single root, capturing typed failures as item errors."""
    root_str = str(Path(root))
    try:
        result = analyze_directory(root, dna_path=dna_path, profile_name=profile_name)
    except SemanticDriftError as exc:
        return BatchItemResult(
            root=root_str,
            ok=False,
            error=str(exc),
            error_type=type(exc).__name__,
        )
    except FileNotFoundError as exc:
        return BatchItemResult(
            root=root_str,
            ok=False,
            error=str(exc),
            error_type="FileNotFoundError",
        )
    return BatchItemResult(root=root_str, ok=True, result=result)


def check_batch(
    roots: Sequence[str | Path],
    dna_path: str | Path | None = None,
    profile_name: str | None = None,
) -> BatchReport:
    """Check every root independently and aggregate results.

    Pure with respect to process globals: safe to parallelize by mapping
    ``check_one`` over roots and assembling a ``BatchReport``.
    """
    items = [check_one(root, dna_path=dna_path, profile_name=profile_name) for root in roots]
    return BatchReport(items=items)


def resolve_roots(
    roots: Iterable[str] | None = None,
    manifest: str | Path | None = None,
) -> list[str]:
    """Combine positional roots with a manifest into a deduplicated list."""
    resolved: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        key = str(Path(raw).resolve()) if Path(raw).exists() else str(Path(raw))
        if key not in seen:
            seen.add(key)
            resolved.append(raw if Path(raw).exists() else key)

    if manifest is not None:
        for item in load_manifest(manifest):
            _add(item)
    if roots:
        for item in roots:
            _add(item)
    return resolved


__all__ = [
    "BatchItemResult",
    "BatchReport",
    "check_batch",
    "check_one",
    "load_manifest",
    "resolve_roots",
]
