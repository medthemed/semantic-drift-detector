"""Regression tests for the two scan fixes shipped in 0.6.0.

1. Stale snapshot replay: ``analyze_directory`` used to reuse the
   modules/edges stored in ``dna.toml`` when a DNA file was present at
   the root, so edits made after ``sdd snapshot`` were silently missed.
2. Skip-dir false positive: ``iter_python_files`` matched ``SKIP_DIRS``
   against the *absolute* path, so a project living under a directory
   named ``build`` / ``dist`` / ``venv`` scanned as zero files.
"""

from __future__ import annotations

from pathlib import Path

from semantic_drift_detector import analyze_directory
from semantic_drift_detector.cli import EXIT_DRIFT, EXIT_OK, main
from semantic_drift_detector.parser import iter_python_files

from conftest import write_py


def _make_drift(root: Path) -> None:
    write_py(
        root / "src" / "myapp" / "domain" / "order.py",
        """
        from myapp.adapters.payment import charge

        def place_order(amount: float) -> None:
            charge(amount)
        """,
    )


class TestCheckRescansTree:
    def test_check_reflects_edits_after_snapshot(self, clean_tree: Path, capsys):
        assert main(["snapshot", str(clean_tree)]) == EXIT_OK
        capsys.readouterr()

        before = analyze_directory(clean_tree)
        assert before.breached is False

        _make_drift(clean_tree)

        after = analyze_directory(clean_tree)
        assert "src/myapp/domain/order.py" in after.checked_files
        assert after.breached is True

    def test_cli_check_detects_drift_introduced_after_snapshot(
        self, clean_tree: Path, capsys
    ):
        assert main(["snapshot", str(clean_tree)]) == EXIT_OK
        capsys.readouterr()
        _make_drift(clean_tree)
        code = main(["check", str(clean_tree)])
        assert code == EXIT_DRIFT


class TestSkipDirsOnlyInsideTree:
    def test_project_under_build_dir_is_scanned(self, tmp_path: Path):
        root = tmp_path / "build" / "proj"
        write_py(root / "src" / "pkg" / "a.py", "x = 1\n")
        write_py(root / "build" / "inner.py", "y = 2\n")  # nested: still skipped
        files = iter_python_files(root)
        rel = [p.relative_to(root).as_posix() for p in files]
        assert rel == ["src/pkg/a.py"]

    def test_analyze_tree_under_dist_dir(self, tmp_path: Path):
        root = tmp_path / "dist" / "proj"
        write_py(root / "src" / "pkg" / "__init__.py", "")
        write_py(root / "src" / "pkg" / "core.py", "x = 1\n")
        result = analyze_directory(root)
        assert len(result.checked_files) == 2
