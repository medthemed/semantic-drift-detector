"""Batch check tests: multi-tree fixture, manifest loading, CLI, pure core."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from semantic_drift_detector.batch import (
    check_batch,
    check_one,
    load_manifest,
    resolve_roots,
)
from semantic_drift_detector.cli import EXIT_DRIFT, EXIT_OK, EXIT_USAGE, main
from tests.conftest import write_py


def _make_second_clean_tree(tmp_path: Path) -> Path:
    root = tmp_path / "other_clean"
    write_py(
        root / "src" / "other" / "domain" / "thing.py",
        """
        class Thing:
            pass
        """,
    )
    write_py(
        root / "src" / "other" / "app.py",
        """
        from other.domain.thing import Thing

        def run() -> Thing:
            return Thing()
        """,
    )
    return root


def test_check_batch_mixed_trees(clean_tree: Path, drifted_tree: Path):
    report = check_batch([clean_tree, drifted_tree])
    assert len(report.items) == 2
    assert report.ok_count == 1
    assert report.breached_count == 1
    assert report.any_breached
    assert not report.any_error
    by_root = {Path(item.root).name: item for item in report.items}
    assert by_root["clean_app"].ok
    assert not by_root["clean_app"].breached
    assert by_root["drifted_app"].ok
    assert by_root["drifted_app"].breached


def test_check_batch_multi_tree_all_ok(clean_tree: Path, tmp_path: Path):
    other = _make_second_clean_tree(tmp_path)
    report = check_batch([clean_tree, other])
    assert report.ok_count == 2
    assert report.breached_count == 0
    assert not report.any_breached


def test_check_batch_records_missing_root(tmp_path: Path):
    missing = tmp_path / "nope"
    report = check_batch([missing])
    assert report.error_count == 1
    assert report.any_error
    assert report.items[0].error_type == "DirectoryNotFoundError"


def test_check_one_returns_item(clean_tree: Path):
    item = check_one(clean_tree)
    assert item.ok
    assert item.result is not None
    assert item.result.mode == "directory"
    assert not item.breached


def test_check_batch_is_pure_and_parallel_safe(clean_tree: Path, drifted_tree: Path):
    """Same inputs → same outputs; concurrent map is safe (no shared state)."""
    seq = check_batch([clean_tree, drifted_tree])
    roots = [clean_tree, drifted_tree]

    def _one(root):
        return check_one(root)

    with ThreadPoolExecutor(max_workers=4) as pool:
        par_items = list(pool.map(_one, roots))
    par_breached = [item.breached for item in par_items]
    seq_breached = [item.breached for item in seq.items]
    assert par_breached == seq_breached


def test_load_manifest(tmp_path: Path, clean_tree: Path):
    other = _make_second_clean_tree(tmp_path)
    manifest = tmp_path / "roots.txt"
    manifest.write_text(
        f"# project roots\n{clean_tree}\n\n{other.name}\n",
        encoding="utf-8",
    )
    roots = load_manifest(manifest)
    assert len(roots) == 2
    assert Path(roots[0]) == clean_tree.resolve()
    assert Path(roots[1]).name == other.name


def test_load_manifest_missing(tmp_path: Path):
    try:
        load_manifest(tmp_path / "missing.txt")
    except FileNotFoundError as exc:
        assert "manifest not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_resolve_roots_dedup(clean_tree: Path, tmp_path: Path):
    manifest = tmp_path / "m.txt"
    manifest.write_text(f"{clean_tree}\n", encoding="utf-8")
    roots = resolve_roots([str(clean_tree)], manifest=manifest)
    assert len(roots) == 1


def test_cli_check_batch_positional(clean_tree: Path, drifted_tree: Path, capsys):
    code = main(["check-batch", str(clean_tree), str(drifted_tree)])
    assert code == EXIT_DRIFT
    out = capsys.readouterr().out
    assert "batch report" in out
    assert "DRIFT" in out
    assert "OK" in out


def test_cli_check_batch_json(clean_tree: Path, drifted_tree: Path, capsys):
    code = main(["check-batch", str(clean_tree), str(drifted_tree), "--json"])
    assert code == EXIT_DRIFT
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["breached"] == 1
    assert payload["summary"]["ok"] == 1
    assert len(payload["items"]) == 2


def test_cli_check_batch_manifest(tmp_path: Path, clean_tree: Path, capsys):
    manifest = tmp_path / "roots.txt"
    manifest.write_text(f"{clean_tree}\n", encoding="utf-8")
    code = main(["check-batch", "--manifest", str(manifest)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "STATUS: OK" in out


def test_cli_check_batch_no_roots():
    code = main(["check-batch"])
    assert code == EXIT_USAGE


def test_cli_check_batch_missing_manifest(tmp_path: Path):
    code = main(["check-batch", "--manifest", str(tmp_path / "nope.txt")])
    assert code == EXIT_USAGE


def test_cli_check_batch_error_root(tmp_path: Path, capsys):
    code = main(["check-batch", str(tmp_path / "missing-root")])
    assert code == EXIT_USAGE
    out = capsys.readouterr().out
    assert "ERROR" in out
