"""Shared fixtures and helpers for semantic-drift-detector tests."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from semantic_drift_detector.types import (
    DNAProfile,
    DNARules,
    ForbiddenEdge,
    LayerSpec,
    NamingRule,
)


def write_py(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture
def clean_tree(tmp_path: Path) -> Path:
    """A clean layered project: domain ← application ← interfaces; adapters beside."""
    root = tmp_path / "clean_app"
    write_py(
        root / "src" / "myapp" / "domain" / "__init__.py",
        "",
    )
    write_py(
        root / "src" / "myapp" / "domain" / "user.py",
        """
        from dataclasses import dataclass

        @dataclass
        class User:
            id: str
            email: str
        """,
    )
    write_py(
        root / "src" / "myapp" / "application" / "__init__.py",
        "",
    )
    write_py(
        root / "src" / "myapp" / "application" / "user_service.py",
        """
        from myapp.domain.user import User

        def get_user(user_id: str) -> User:
            return User(id=user_id, email="a@b.c")
        """,
    )
    write_py(
        root / "src" / "myapp" / "adapters" / "__init__.py",
        "",
    )
    write_py(
        root / "src" / "myapp" / "adapters" / "user_repo.py",
        """
        from myapp.domain.user import User

        class UserRepository:
            def find(self, user_id: str) -> User:
                return User(id=user_id, email="repo@example.com")
        """,
    )
    write_py(
        root / "src" / "myapp" / "interfaces" / "__init__.py",
        "",
    )
    write_py(
        root / "src" / "myapp" / "interfaces" / "api.py",
        """
        from myapp.application.user_service import get_user

        def handle(user_id: str) -> str:
            return get_user(user_id).email
        """,
    )
    return root


@pytest.fixture
def drifted_tree(tmp_path: Path) -> Path:
    """A tree that violates layering: domain imports adapters."""
    root = tmp_path / "drifted_app"
    write_py(
        root / "src" / "myapp" / "domain" / "order.py",
        """
        from myapp.adapters.payment import charge

        def place_order(amount: float) -> None:
            charge(amount)
        """,
    )
    write_py(
        root / "src" / "myapp" / "adapters" / "payment.py",
        """
        def charge(amount: float) -> bool:
            return amount > 0
        """,
    )
    write_py(
        root / "src" / "myapp" / "domain" / "BadName.py",
        """
        class snake_case_class:
            pass
        """,
    )
    return root


@pytest.fixture
def strict_rules() -> DNARules:
    return DNARules(
        layers=[
            LayerSpec(name="domain", prefixes=["myapp.domain", "domain"]),
            LayerSpec(name="application", prefixes=["myapp.application", "application"]),
            LayerSpec(name="adapters", prefixes=["myapp.adapters", "adapters"]),
            LayerSpec(name="interfaces", prefixes=["myapp.interfaces", "interfaces"]),
        ],
        forbidden_edges=[
            ForbiddenEdge(from_layer="domain", to_layer="adapters", reason="domain must not import adapters"),
            ForbiddenEdge(from_layer="domain", to_layer="interfaces", reason="domain must not import interfaces"),
            ForbiddenEdge(from_layer="application", to_layer="adapters", reason="application must not import adapters"),
        ],
        naming=[
            NamingRule(kind="module", pattern=r"^[a-z_][a-z0-9_]*$", message="modules must be snake_case"),
            NamingRule(kind="class", pattern=r"^[A-Z][A-Za-z0-9]*$", message="classes must be PascalCase"),
        ],
        required_patterns=[],
        allowed_roots=["myapp"],
        entropy_threshold=0.25,
    )


@pytest.fixture
def clean_dna(clean_tree: Path, strict_rules: DNARules) -> DNAProfile:
    from semantic_drift_detector.profile import extract_dna

    return extract_dna(clean_tree, rules=strict_rules)
