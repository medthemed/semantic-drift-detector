"""Polling watch mode: re-check a tree whenever its fingerprint changes.

The loop is intentionally dependency-free (no OS file watchers): a cheap
fingerprint — ``(relative path, mtime_ns, size)`` for every Python file in
the tree plus any root DNA profile — is polled on an interval, and the
drift check only re-runs when the fingerprint changes. An event is only
*reported* when the check result itself changed since the last reported
result, so cosmetic saves that do not affect the outcome stay quiet.

``watch_events`` is a generator so tests (and embedders) can bound the
loop with ``max_polls`` / ``once`` instead of hanging forever.
``run_watch`` is the callback-collecting helper used by the CLI; it stops
cleanly on ``KeyboardInterrupt`` and returns the events seen so far.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.errors import DirectoryNotFoundError
from semantic_drift_detector.parser import iter_python_files, relative_posix
from semantic_drift_detector.profile import DNA_FILENAMES
from semantic_drift_detector.types import CheckResult

# One entry per file: (relative POSIX path, mtime_ns, size_bytes).
FingerprintEntry = tuple[str, int, int]
Fingerprint = tuple[FingerprintEntry, ...]


def directory_fingerprint(
    root: str | Path, exclude: list[str] | None = None
) -> Fingerprint:
    """Fingerprint a tree from file mtimes + sizes (no content reads).

    Covers every Python file the scanner would read (same skip rules as
    :func:`semantic_drift_detector.parser.iter_python_files`) plus a root
    DNA profile file (``dna.toml`` / ``dna.yaml`` / ``dna.yml`` /
    ``dna.json``) when present, since rule changes affect results too.

    Files that disappear mid-walk are skipped. The result is a sorted,
    hashable tuple: equal trees produce equal fingerprints.

    Raises
    ------
    DirectoryNotFoundError
        If ``root`` does not exist.
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise DirectoryNotFoundError(str(root_path))

    entries: dict[str, FingerprintEntry] = {}
    for path in iter_python_files(root_path, exclude=exclude):
        rel = relative_posix(path, root_path)
        try:
            stat = path.stat()
        except OSError:
            continue
        entries[rel] = (rel, stat.st_mtime_ns, stat.st_size)

    for name in DNA_FILENAMES:
        candidate = root_path / name
        if candidate.is_file():
            try:
                stat = candidate.stat()
            except OSError:
                continue
            entries[name] = (name, stat.st_mtime_ns, stat.st_size)

    return tuple(entries[key] for key in sorted(entries))


def _result_signature(result: CheckResult) -> str:
    """Stable comparison key for 'did the outcome change?'."""
    return json.dumps(result.to_dict(), sort_keys=True)


@dataclass
class WatchEvent:
    """One reported watch outcome (initial check or a changed result)."""

    root: str
    result: CheckResult
    fingerprint: Fingerprint = ()
    initial: bool = False

    @property
    def breached(self) -> bool:
        return bool(self.result is not None and self.result.breached)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "initial": self.initial,
            "breached": self.breached,
            "result": self.result.to_dict() if self.result is not None else None,
        }


def watch_events(
    root: str | Path,
    interval: float = 2.0,
    dna_path: str | Path | None = None,
    profile_name: str | None = None,
    *,
    max_polls: int | None = None,
    once: bool = False,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Iterator[WatchEvent]:
    """Yield a :class:`WatchEvent` for the initial check and each change.

    The first poll always runs the check and yields an event
    (``initial=True``). Later polls recompute the fingerprint; the check
    re-runs only when it changed, and an event is yielded only when the
    new result differs from the last reported one.

    Parameters
    ----------
    interval:
        Seconds between polls. Must be positive unless ``once``.
    max_polls:
        Bound the total number of polls (initial poll included). ``None``
        polls forever (until the consumer stops / Ctrl-C).
    once:
        Single-pass mode: exactly one poll, no sleeping.
    sleep_fn:
        Injectable sleep, for tests.

    Raises
    ------
    ValueError
        If ``interval`` is not positive (and not ``once``), or
        ``max_polls`` is less than 1.
    DirectoryNotFoundError
        If ``root`` does not exist.
    """
    if once:
        max_polls = 1
    elif interval <= 0:
        raise ValueError(f"interval must be positive, got {interval!r}")
    if max_polls is not None and max_polls < 1:
        raise ValueError(f"max_polls must be >= 1, got {max_polls!r}")

    root_path = Path(root).resolve()
    if not root_path.exists():
        raise DirectoryNotFoundError(str(root_path))

    last_fingerprint = directory_fingerprint(root_path)
    result = analyze_directory(root_path, dna_path=dna_path, profile_name=profile_name)
    last_signature = _result_signature(result)
    yield WatchEvent(
        root=str(root_path), result=result, fingerprint=last_fingerprint, initial=True
    )

    polls = 1
    while max_polls is None or polls < max_polls:
        sleep_fn(interval)
        polls += 1
        fingerprint = directory_fingerprint(root_path)
        if fingerprint == last_fingerprint:
            continue
        last_fingerprint = fingerprint
        result = analyze_directory(
            root_path, dna_path=dna_path, profile_name=profile_name
        )
        signature = _result_signature(result)
        if signature == last_signature:
            continue
        last_signature = signature
        yield WatchEvent(root=str(root_path), result=result, fingerprint=fingerprint)


def run_watch(
    root: str | Path,
    interval: float = 2.0,
    dna_path: str | Path | None = None,
    profile_name: str | None = None,
    *,
    max_polls: int | None = None,
    once: bool = False,
    sleep_fn: Callable[[float], None] = time.sleep,
    on_event: Callable[[WatchEvent], None] | None = None,
) -> list[WatchEvent]:
    """Run the watch loop, collecting (and optionally reporting) events.

    Stops cleanly on ``KeyboardInterrupt`` — events gathered so far are
    returned and no exception propagates, so the CLI can exit without a
    traceback on Ctrl-C.
    """
    events: list[WatchEvent] = []
    try:
        for event in watch_events(
            root,
            interval=interval,
            dna_path=dna_path,
            profile_name=profile_name,
            max_polls=max_polls,
            once=once,
            sleep_fn=sleep_fn,
        ):
            events.append(event)
            if on_event is not None:
                on_event(event)
    except KeyboardInterrupt:
        pass
    return events


__all__ = [
    "Fingerprint",
    "FingerprintEntry",
    "WatchEvent",
    "directory_fingerprint",
    "run_watch",
    "watch_events",
]
