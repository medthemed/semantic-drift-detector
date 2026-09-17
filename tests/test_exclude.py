"""Tests for rules.exclude path globs."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.parser import (
    build_snapshot,
    iter_python_files,
    path_excluded,
)
from semantic_drift_detector.profile import extract_dna, load_dna, save_dna
from semantic_drift_detector.types import DNARules


def write_py(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip("\n"), encoding="utf-8")
    return path


def test_path_excluded_glob_basics():
    patterns = ["**/migrations/**", "scripts/sandbox/*"]
    assert path_excluded("src/app/migrations/001.py", patterns)
    assert path_excluded("src/app/migrations", patterns)
    assert path_excluded("scripts/sandbox/scratch.py", patterns)
    assert not path_excluded("src/app/domain/user.py", patterns)
    assert not path_excluded("scripts/prod.py", patterns)
    assert not path_excluded("anything.py", [])


def test_path_excluded_double_star_depth():
    assert path_excluded("a/b/c/d.py", ["a/**"])
    assert path_excluded("a/x.py", ["a/**"])
    assert path_excluded("deep/nested/tree/leaf.py", ["**/tree/**"])
    assert not path_excluded("b/x.py", ["a/**"])


def test_iter_python_files_applies_exclude(tmp_path: Path):
    write_py(tmp_path / "src" / "app" / "domain" / "user.py", "x = 1\n")
    write_py(tmp_path / "src" / "app" / "migrations" / "001.py", "y = 2\n")
    write_py(tmp_path / "scripts" / "sandbox" / "scratch.py", "z = 3\n")

    all_files = iter_python_files(tmp_path)
    assert len(all_files) == 3

    kept = iter_python_files(
        tmp_path, exclude=["**/migrations/**", "scripts/sandbox/*"]
    )
    rels = {p.relative_to(tmp_path).as_posix() for p in kept}
    assert rels == {"src/app/domain/user.py"}


def test_build_snapshot_exclude(tmp_path: Path):
    write_py(tmp_path / "src" / "app" / "domain" / "user.py", "class User: pass\n")
    write_py(tmp_path / "src" / "app" / "migrations" / "001.py", "class M: pass\n")

    modules, edges = build_snapshot(tmp_path, exclude=["**/migrations/**"])
    names = {m.module for m in modules}
    assert any("domain" in n for n in names)
    assert not any("migrations" in n for n in names)
    assert edges == [] or all("migrations" not in e.source for e in edges)


def test_extract_dna_honors_rules_exclude(tmp_path: Path):
    write_py(tmp_path / "src" / "app" / "domain" / "user.py", "class User: pass\n")
    write_py(tmp_path / "src" / "app" / "migrations" / "001.py", "class M: pass\n")

    rules = DNARules(exclude=["**/migrations/**"], entropy_threshold=0.5)
    dna = extract_dna(tmp_path, rules=rules)
    paths = [m.path for m in dna.modules]
    assert any("domain" in p for p in paths)
    assert not any("migrations" in p for p in paths)


def test_exclude_roundtrips_toml_and_json(tmp_path: Path):
    rules = DNARules(exclude=["**/generated/**", "vendor/*"])
    dna = extract_dna(tmp_path, rules=rules)
    # empty tree is fine; we only care about rules serialization

    toml_path = tmp_path / "dna.toml"
    save_dna(dna, toml_path)
    text = toml_path.read_text(encoding="utf-8")
    assert "exclude" in text
    loaded = load_dna(toml_path)
    assert loaded.rules.exclude == ["**/generated/**", "vendor/*"]

    json_path = tmp_path / "dna.json"
    save_dna(dna, json_path)
    loaded_json = load_dna(json_path)
    assert loaded_json.rules.exclude == ["**/generated/**", "vendor/*"]


def test_analyze_directory_skips_excluded(tmp_path: Path, clean_tree: Path):
    # Inject a migrations package that would otherwise be scanned
    write_py(
        clean_tree / "src" / "myapp" / "migrations" / "001_init.py",
        """
        from myapp.domain.user import User

        def upgrade():
            return User(id="1", email="a@b.c")
        """,
    )
    rules = DNARules(
        exclude=["**/migrations/**"],
        entropy_threshold=0.25,
        allowed_roots=["myapp"],
    )
    dna = extract_dna(clean_tree, rules=rules)
    dna_path = tmp_path / "dna.toml"
    save_dna(dna, dna_path)

    result = analyze_directory(clean_tree, dna_path=dna_path)
    assert not any("migrations" in f for f in result.checked_files)


def test_cli_snapshot_and_check_with_exclude(clean_tree: Path, capsys):
    from semantic_drift_detector.cli import EXIT_OK, main

    write_py(
        clean_tree / "src" / "myapp" / "migrations" / "001.py",
        "from myapp.domain.user import User\n",
    )
    rules = DNARules(exclude=["**/migrations/**"], entropy_threshold=0.5)
    dna = extract_dna(clean_tree, rules=rules)
    dna_path = clean_tree / "dna.toml"
    save_dna(dna, dna_path)

    code = main(["check", str(clean_tree), "--dna", str(dna_path), "--json"])
    assert code in (EXIT_OK, 1)
    out = capsys.readouterr().out
    assert "migrations" not in out
