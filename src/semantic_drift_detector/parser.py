"""Parse Python sources into module records and import edges."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from semantic_drift_detector.types import ImportEdge, ModuleInfo

# Directories skipped when walking a tree
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".eggs",
}

# Common stdlib roots we never treat as project packages.
STDLIB_ROOTS = {
    "abc",
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "collections",
    "contextlib",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "glob",
    "hashlib",
    "http",
    "importlib",
    "inspect",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "pickle",
    "re",
    "shutil",
    "socket",
    "sqlite3",
    "statistics",
    "string",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "typing",
    "unittest",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "xml",
    "zipfile",
}


def is_python_file(path: Path) -> bool:
    return path.suffix == ".py" and path.is_file()


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a POSIX-style glob into a compiled regex.

    Supports ``*`` (no slash), ``**`` (any depth including none), and ``?``.
    Anchored to the full relative path.
    """
    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # ** — match across path separators
                if i + 2 < n and pattern[i + 2] == "/":
                    parts.append("(?:.*/)?")
                    i += 3
                else:
                    parts.append(".*")
                    i += 2
            else:
                parts.append("[^/]*")
                i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def path_excluded(rel_path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    """True if relative POSIX path matches any exclude glob.

    Patterns are matched against the path as given (e.g. ``src/app/migrations/001.py``).
    A trailing ``/**`` also excludes the directory itself.
    """
    if not patterns:
        return False
    norm = rel_path.replace("\\", "/").lstrip("./")
    for pattern in patterns:
        if not pattern:
            continue
        if _glob_to_regex(pattern).match(norm):
            return True
        # ``dir/**`` should also drop the directory node, not only its children
        if pattern.endswith("/**"):
            dir_pattern = pattern[:-3]
            if dir_pattern and _glob_to_regex(dir_pattern).match(norm):
                return True
    return False


def filter_excluded(
    paths: list[Path], root: Path, exclude: list[str] | None
) -> list[Path]:
    if not exclude:
        return paths
    kept: list[Path] = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        if path_excluded(rel, exclude):
            continue
        kept.append(path)
    return kept


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def path_to_module(rel_path: str) -> str:
    """Convert a relative posix path like 'src/app/domain/user.py' to a dotted module.

    Strips a leading 'src/' if present so package roots match conventional layouts.
    """
    p = rel_path.replace("\\", "/")
    if p.endswith("/__init__.py"):
        p = p[: -len("/__init__.py")]
    elif p.endswith(".py"):
        p = p[: -len(".py")]
    parts = [part for part in p.split("/") if part and part != "."]
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def iter_python_files(root: Path, exclude: list[str] | None = None) -> list[Path]:
    files: list[Path] = []
    root = root.resolve()
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        files.append(path)
    return filter_excluded(files, root, exclude)


def _module_from_import(node: ast.AST, level: int, current_module: str) -> str | None:
    """Resolve an ImportFrom node to a dotted module string (best-effort)."""
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        names = [alias.name for alias in node.names if alias.name != "*"]
        if level and level > 0:
            parts = current_module.split(".")
            package_parts = parts[:-1] if parts else []
            up = level - 1
            if up > len(package_parts):
                return None
            base = package_parts[: len(package_parts) - up] if up else package_parts
            if module:
                target = ".".join([*base, module]) if base else module
            else:
                target = ".".join(base) if base else None
            if not target:
                return None
            if names:
                return ".".join([target, names[0]])
            return target
        if not module:
            return None
        if names:
            return ".".join([module, names[0]])
        return module
    return None


def extract_imports(tree: ast.AST, current_module: str) -> list[str]:
    """Extract dotted import targets from an AST."""
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _module_from_import(node, node.level or 0, current_module)
            if resolved:
                imports.append(resolved)
    seen: set[str] = set()
    unique: list[str] = []
    for item in imports:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def extract_definitions(tree: ast.AST) -> tuple[list[str], list[str]]:
    """Return (class_names, function_names) at any nesting level."""
    classes: list[str] = []
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
    return classes, functions


def parse_file(path: Path, root: Path) -> tuple[ModuleInfo, list[ImportEdge]]:
    """Parse one Python file into ModuleInfo plus outgoing ImportEdges."""
    rel = relative_posix(path, root)
    module = path_to_module(rel)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ModuleInfo(path=rel, module=module), []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return ModuleInfo(path=rel, module=module), []

    imports = extract_imports(tree, module)
    classes, functions = extract_definitions(tree)
    info = ModuleInfo(
        path=rel,
        module=module,
        imports=imports,
        classes=classes,
        functions=functions,
    )
    edges = [ImportEdge(source=module, target=imp, file=rel) for imp in imports]
    return info, edges


def build_snapshot(
    root: Path, exclude: list[str] | None = None
) -> tuple[list[ModuleInfo], list[ImportEdge]]:
    """Walk a directory and build module + edge lists.

    Paths matching ``exclude`` globs (relative POSIX paths) are skipped.
    """
    root = root.resolve()
    modules: list[ModuleInfo] = []
    edges: list[ImportEdge] = []
    for path in iter_python_files(root, exclude=exclude):
        info, file_edges = parse_file(path, root)
        modules.append(info)
        edges.extend(file_edges)
    return modules, edges


def infer_allowed_roots(modules: list[ModuleInfo]) -> list[str]:
    """Infer top-level package roots from discovered modules."""
    roots: set[str] = set()
    for mod in modules:
        if not mod.module:
            continue
        root = mod.module.split(".", 1)[0]
        roots.add(root)
    return sorted(roots)


def is_project_import(target: str, allowed_roots: list[str]) -> bool:
    """True if target looks like an internal/project import."""
    if not target:
        return False
    root = target.split(".", 1)[0]
    if not allowed_roots:
        return root not in STDLIB_ROOTS
    return root in allowed_roots
