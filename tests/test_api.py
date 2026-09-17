"""Public API surface, typed exceptions, and integration coverage."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

import semantic_drift_detector as sdd
from semantic_drift_detector.errors import (
    DirectoryNotFoundError,
    DnaFileNotFoundError,
    DnaProfileError,
    InvalidDnaError,
    SemanticDriftError,
)
from semantic_drift_detector.profile import load_dna, load_profile, save_dna


def _write_py(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture
def tiny_tree(tmp_path: Path) -> Path:
    """A minimal layered project used for the integration path."""
    root = tmp_path / "tiny_app"
    _write_py(root / "src" / "myapp" / "domain" / "__init__.py", "")
    _write_py(
        root / "src" / "myapp" / "domain" / "item.py",
        """
        class Item:
            pass
        """,
    )
    _write_py(root / "src" / "myapp" / "application" / "__init__.py", "")
    _write_py(
        root / "src" / "myapp" / "application" / "item_service.py",
        """
        from myapp.domain.item import Item

        def load() -> Item:
            return Item()
        """,
    )
    _write_py(root / "src" / "myapp" / "adapters" / "__init__.py", "")
    _write_py(
        root / "src" / "myapp" / "adapters" / "item_repo.py",
        """
        from myapp.domain.item import Item

        class ItemRepo:
            def get(self) -> Item:
                return Item()
        """,
    )
    return root


class TestExceptionHierarchy:
    def test_base_is_exception(self):
        assert issubclass(SemanticDriftError, Exception)

    def test_directory_error_is_filnotfound(self):
        assert issubclass(DirectoryNotFoundError, FileNotFoundError)
        assert issubclass(DirectoryNotFoundError, SemanticDriftError)

    def test_dna_errors_share_profile_base(self):
        assert issubclass(DnaFileNotFoundError, DnaProfileError)
        assert issubclass(InvalidDnaError, DnaProfileError)
        assert issubclass(DnaProfileError, SemanticDriftError)

    def test_builtin_compatibility(self):
        assert issubclass(DnaFileNotFoundError, FileNotFoundError)
        assert issubclass(InvalidDnaError, ValueError)


class TestTypedRaise:
    def test_analyze_missing_directory(self, tmp_path: Path):
        with pytest.raises(DirectoryNotFoundError) as exc_info:
            sdd.analyze_directory(tmp_path / "nope")
        assert "nope" in str(exc_info.value)

    def test_load_profile_missing_file(self, tmp_path: Path):
        with pytest.raises(DnaFileNotFoundError) as exc_info:
            load_profile(tmp_path / "missing-dna.toml")
        assert exc_info.value.path.endswith("missing-dna.toml")

    def test_load_profile_invalid_json(self, tmp_path: Path):
        bad = tmp_path / "dna.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(InvalidDnaError):
            load_profile(bad)

    def test_legacy_catch_still_works(self, tmp_path: Path):
        try:
            sdd.analyze_directory(tmp_path / "gone")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError-compatible error")


class TestPublicExports:
    def test_all_lists_core_api(self):
        for name in (
            "analyze_directory",
            "analyze_diff",
            "compute_entropy",
            "extract_dna",
            "load_profile",
            "render_json",
            "render_text",
            "save_dna",
            "SemanticDriftError",
        ):
            assert name in sdd.__all__
            assert hasattr(sdd, name)

    def test_load_profile_matches_load_dna(self, tiny_tree: Path, tmp_path: Path):
        profile = sdd.extract_dna(tiny_tree)
        path = tmp_path / "dna.toml"
        save_dna(profile, path)
        via_alias = load_profile(path)
        via_old = load_dna(path)
        assert via_alias.to_dict() == via_old.to_dict()


class TestIntegration:
    def test_snapshot_check_roundtrip_on_tiny_tree(self, tiny_tree: Path, capsys):
        """End-to-end: extract DNA, persist, reload, analyze directory."""
        from semantic_drift_detector.cli import EXIT_OK, main

        code = main(["snapshot", str(tiny_tree)])
        assert code == EXIT_OK
        dna_path = tiny_tree / "dna.toml"
        assert dna_path.is_file()

        profile = load_profile(dna_path)
        assert len(profile.modules) >= 3
        assert profile.rules.layers

        result = sdd.analyze_directory(tiny_tree, dna_path=dna_path)
        assert result.mode == "directory"
        assert result.entropy is not None
        assert 0.0 <= result.entropy.value <= 1.0
        assert result.checked_files
        # Clean layered tree should not produce layer errors
        assert not result.errors

    def test_cli_check_uses_loaded_profile(self, tiny_tree: Path, capsys):
        from semantic_drift_detector.cli import EXIT_OK, main

        assert main(["snapshot", str(tiny_tree)]) == EXIT_OK
        capsys.readouterr()
        code = main(["check", str(tiny_tree), "--json"])
        assert code in (EXIT_OK, 1)
        out = capsys.readouterr().out
        assert '"entropy"' in out
        assert '"breached"' in out
