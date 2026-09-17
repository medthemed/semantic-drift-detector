"""Named architecture profiles in dna.toml and --profile CLI flag."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from semantic_drift_detector import select_profile
from semantic_drift_detector.cli import EXIT_OK, EXIT_USAGE, main
from semantic_drift_detector.errors import UnknownProfileError
from semantic_drift_detector.profile import (
    load_profile,
    merge_profile_overrides,
    save_dna,
)
from semantic_drift_detector.types import DNAProfile, DNARules


def _write_py(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture
def profiled_tree(tmp_path: Path) -> Path:
    """Layered tree with a dna.toml that defines default + strict profiles."""
    root = tmp_path / "profiled_app"
    _write_py(root / "src" / "myapp" / "domain" / "__init__.py", "")
    _write_py(
        root / "src" / "myapp" / "domain" / "user.py",
        """
        class User:
            pass
        """,
    )
    _write_py(root / "src" / "myapp" / "application" / "__init__.py", "")
    _write_py(
        root / "src" / "myapp" / "application" / "user_service.py",
        """
        from myapp.domain.user import User

        def load() -> User:
            return User()
        """,
    )
    dna = root / "dna.toml"
    dna.write_text(
        dedent(
            """
            project_root = ""

            [rules]
            entropy_threshold = 0.3
            allowed_roots = ["myapp"]

            [[rules.layers]]
            name = "domain"
            prefixes = ["myapp.domain"]

            [[rules.layers]]
            name = "application"
            prefixes = ["myapp.application"]

            [profiles.default]
            entropy_threshold = 0.3

            [profiles.strict]
            entropy_threshold = 0.05
            allowed_roots = ["myapp"]

            [profiles.relaxed]
            entropy_threshold = 0.8
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return root


class TestSelectProfile:
    def test_default_returns_base_rules(self):
        base = DNARules(entropy_threshold=0.25)
        profile = DNAProfile(rules=base, profiles={"strict": {"entropy_threshold": 0.05}})
        assert select_profile(profile, None) is base
        assert select_profile(profile, "default") is base

    def test_named_profile_overrides_threshold(self):
        base = DNARules(entropy_threshold=0.25, allowed_roots=["myapp"])
        profile = DNAProfile(
            rules=base,
            profiles={"strict": {"entropy_threshold": 0.05}},
        )
        strict = select_profile(profile, "strict")
        assert strict.entropy_threshold == 0.05
        assert strict.allowed_roots == ["myapp"]  # inherited

    def test_unknown_profile_raises(self):
        profile = DNAProfile(rules=DNARules(), profiles={"strict": {}})
        with pytest.raises(UnknownProfileError) as exc_info:
            select_profile(profile, "turbo")
        assert "turbo" in str(exc_info.value)
        assert "strict" in str(exc_info.value)

    def test_merge_replaces_lists_when_provided(self):
        base = DNARules(entropy_threshold=0.25, exclude=["a/**"], allowed_roots=["x"])
        merged = merge_profile_overrides(
            base, {"entropy_threshold": 0.1, "exclude": ["b/**"]}
        )
        assert merged.exclude == ["b/**"]
        assert merged.allowed_roots == ["x"]
        assert merged.entropy_threshold == 0.1


class TestProfileRoundtrip:
    def test_load_profiles_from_dna_toml(self, profiled_tree: Path):
        profile = load_profile(profiled_tree / "dna.toml")
        assert set(profile.profiles) == {"default", "strict", "relaxed"}
        assert profile.profile_names() == ["default", "relaxed", "strict"]
        # "default" always resolves to base [rules], even if a [profiles.default]
        # section documents the same values.
        assert select_profile(profile, "default").entropy_threshold == 0.3
        strict = select_profile(profile, "strict")
        assert strict.entropy_threshold == 0.05
        relaxed = select_profile(profile, "relaxed")
        assert relaxed.entropy_threshold == 0.8

    def test_save_preserves_profiles(self, profiled_tree: Path, tmp_path: Path):
        profile = load_profile(profiled_tree / "dna.toml")
        out = tmp_path / "copy.toml"
        save_dna(profile, out)
        reloaded = load_profile(out)
        assert "strict" in reloaded.profiles
        assert select_profile(reloaded, "strict").entropy_threshold == 0.05


class TestCliProfileFlag:
    def test_check_default_profile(self, profiled_tree: Path, capsys):
        code = main(["check", str(profiled_tree)])
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "STATUS: OK" in out

    def test_check_strict_profile_uses_lower_threshold(self, profiled_tree: Path, capsys):
        # Clean tree still passes even with a very low threshold
        code = main(["check", str(profiled_tree), "--profile", "strict"])
        assert code == EXIT_OK

    def test_check_unknown_profile_exit_2(self, profiled_tree: Path, capsys):
        code = main(["check", str(profiled_tree), "--profile", "nope"])
        assert code == EXIT_USAGE
        err = capsys.readouterr().err
        assert "nope" in err

    def test_check_profile_json_threshold(self, profiled_tree: Path, capsys):
        code = main(["check", str(profiled_tree), "--profile", "strict", "--json"])
        assert code in (EXIT_OK, 1)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["threshold"] == 0.05

    def test_analyze_directory_profile_name(self, profiled_tree: Path):
        from semantic_drift_detector import analyze_directory

        result = analyze_directory(profiled_tree, profile_name="strict")
        assert result.threshold == 0.05
