"""Typed exceptions for semantic-drift-detector.

Callers can catch ``SemanticDriftError`` for any tool failure, or a more
specific subclass. Typed errors also inherit the historical builtins so
existing ``except FileNotFoundError`` / ``except ValueError`` code keeps
working.
"""

from __future__ import annotations


class SemanticDriftError(Exception):
    """Base class for all semantic-drift-detector errors."""


class DirectoryNotFoundError(SemanticDriftError, FileNotFoundError):
    """A target directory does not exist."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Directory not found: {path}")


class DnaProfileError(SemanticDriftError):
    """Base class for DNA profile load and parse failures."""


class DnaFileNotFoundError(DnaProfileError, FileNotFoundError):
    """A DNA profile file is missing on disk."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"DNA profile not found: {path}")


class InvalidDnaError(DnaProfileError, ValueError):
    """DNA profile content is malformed or not a supported mapping."""


class UnknownProfileError(SemanticDriftError, KeyError):
    """A named profile was requested but is not defined in the DNA file."""

    def __init__(self, name: str, available: list[str] | None = None) -> None:
        self.name = name
        self.available = list(available or [])
        detail = f"; available: {', '.join(self.available)}" if self.available else ""
        super().__init__(f"unknown profile {name!r}{detail}")


__all__ = [
    "DirectoryNotFoundError",
    "DnaFileNotFoundError",
    "DnaProfileError",
    "InvalidDnaError",
    "SemanticDriftError",
    "UnknownProfileError",
]
