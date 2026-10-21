"""Watch mode: fingerprint, watch_events/run_watch helpers, and the CLI.

(Regression tests for the scan fixes watch mode depends on — stale
``dna.toml`` replay and skip-dir matching — live in
``tests/test_scan_regressions.py``.)
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from semantic_drift_detector import (
    WatchEvent,
    directory_fingerprint,
    run_watch,
    watch_events,
)
from semantic_drift_detector.cli import EXIT_DRIFT, EXIT_OK, EXIT_USAGE, main
from semantic_drift_detector.errors import DirectoryNotFoundError
from semantic_drift_detector.parser import iter_python_files

from conftest import write_py


def _bump_mtime(path: Path, delta_ns: int = 1_000_000_000) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + delta_ns))


def _make_drift(root: Path) -> None:
    write_py(
        root / "src" / "myapp" / "domain" / "order.py",
        """
        from myapp.adapters.payment import charge

        def place_order(amount: float) -> None:
            charge(amount)
        """,
    )


class TestDirectoryFingerprint:
    def test_stable_for_unchanged_tree(self, clean_tree: Path):
        first = directory_fingerprint(clean_tree)
        second = directory_fingerprint(clean_tree)
        assert first == second
        assert first  # non-empty
        assert all(isinstance(entry, tuple) and len(entry) == 3 for entry in first)

    def test_changes_on_edit(self, clean_tree: Path):
        before = directory_fingerprint(clean_tree)
        target = clean_tree / "src" / "myapp" / "domain" / "user.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# comment\n")
        _bump_mtime(target)
        after = directory_fingerprint(clean_tree)
        assert after != before

    def test_changes_on_new_file(self, clean_tree: Path):
        before = directory_fingerprint(clean_tree)
        write_py(clean_tree / "src" / "myapp" / "domain" / "extra.py", "x = 1\n")
        after = directory_fingerprint(clean_tree)
        assert after != before
        assert len(after) == len(before) + 1

    def test_changes_on_delete(self, clean_tree: Path):
        before = directory_fingerprint(clean_tree)
        (clean_tree / "src" / "myapp" / "domain" / "user.py").unlink()
        after = directory_fingerprint(clean_tree)
        assert after != before
        assert len(after) == len(before) - 1

    def test_ignores_pycache(self, clean_tree: Path):
        before = directory_fingerprint(clean_tree)
        cache = clean_tree / "src" / "myapp" / "__pycache__"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "user.cpython-312.py").write_text("x = 1\n", encoding="utf-8")
        # .py files under __pycache__ are not project sources
        assert directory_fingerprint(clean_tree) == before

    def test_missing_directory_raises(self, tmp_path: Path):
        with pytest.raises(DirectoryNotFoundError):
            directory_fingerprint(tmp_path / "nope")

    def test_tree_under_skip_named_parent_dir(self, tmp_path: Path):
        """Regression: a project inside a folder named 'build' is not empty."""
        root = tmp_path / "build" / "proj"
        write_py(root / "src" / "pkg" / "a.py", "x = 1\n")
        write_py(root / "build" / "inner.py", "y = 2\n")  # nested build dir: skipped
        files = iter_python_files(root)
        rel = [p.relative_to(root).as_posix() for p in files]
        assert rel == ["src/pkg/a.py"]
        fingerprint = directory_fingerprint(root)
        assert [entry[0] for entry in fingerprint] == ["src/pkg/a.py"]

    def test_dna_file_included(self, clean_tree: Path):
        (clean_tree / "dna.toml").write_text("[rules]\n", encoding="utf-8")
        names = [entry[0] for entry in directory_fingerprint(clean_tree)]
        assert "dna.toml" in names


class TestWatchEvents:
    def test_once_yields_single_initial_event(self, clean_tree: Path):
        events = list(watch_events(clean_tree, once=True, sleep_fn=lambda s: None))
        assert len(events) == 1
        assert events[0].initial is True
        assert events[0].result is not None
        assert events[0].breached is False

    def test_no_event_when_nothing_changes(self, clean_tree: Path):
        events = list(
            watch_events(clean_tree, interval=0.01, max_polls=4, sleep_fn=lambda s: None)
        )
        assert len(events) == 1  # initial only

    def test_event_when_result_changes(self, clean_tree: Path):
        state = {"sleeps": 0}

        def fake_sleep(_seconds: float) -> None:
            state["sleeps"] += 1
            if state["sleeps"] == 1:
                _make_drift(clean_tree)

        events = list(
            watch_events(clean_tree, interval=0.01, max_polls=4, sleep_fn=fake_sleep)
        )
        assert len(events) == 2
        assert events[0].initial is True and events[0].breached is False
        assert events[1].initial is False and events[1].breached is True

    def test_no_event_when_change_does_not_affect_result(self, clean_tree: Path):
        state = {"sleeps": 0}

        def fake_sleep(_seconds: float) -> None:
            state["sleeps"] += 1
            if state["sleeps"] == 1:
                target = clean_tree / "src" / "myapp" / "domain" / "user.py"
                target.write_text(
                    target.read_text(encoding="utf-8") + "\n# harmless comment\n"
                )
                _bump_mtime(target)

        events = list(
            watch_events(clean_tree, interval=0.01, max_polls=3, sleep_fn=fake_sleep)
        )
        assert len(events) == 1  # re-checked, but outcome unchanged: quiet

    def test_invalid_interval_rejected(self, clean_tree: Path):
        with pytest.raises(ValueError):
            list(watch_events(clean_tree, interval=0, sleep_fn=lambda s: None))

    def test_invalid_max_polls_rejected(self, clean_tree: Path):
        with pytest.raises(ValueError):
            list(watch_events(clean_tree, max_polls=0, sleep_fn=lambda s: None))

    def test_missing_directory_raises(self, tmp_path: Path):
        with pytest.raises(DirectoryNotFoundError):
            list(watch_events(tmp_path / "gone", once=True))


class TestRunWatch:
    def test_run_watch_collects_and_reports(self, clean_tree: Path):
        reported: list[WatchEvent] = []
        events = run_watch(clean_tree, once=True, on_event=reported.append)
        assert len(events) == 1
        assert reported == events

    def test_run_watch_ctrl_c_exits_cleanly(self, clean_tree: Path):
        def interrupting_sleep(_seconds: float) -> None:
            raise KeyboardInterrupt

        events = run_watch(clean_tree, interval=0.01, sleep_fn=interrupting_sleep)
        # Initial event was delivered; Ctrl-C ends the loop without a traceback.
        assert len(events) == 1
        assert events[0].initial is True

    def test_watch_event_to_dict(self, clean_tree: Path):
        events = run_watch(clean_tree, once=True)
        payload = events[0].to_dict()
        assert payload["initial"] is True
        assert payload["breached"] is False
        assert payload["result"]["mode"] == "directory"


class TestWatchCli:
    def test_cli_watch_once_clean_tree(self, clean_tree: Path, capsys):
        code = main(["watch", str(clean_tree), "--once"])
        assert code == EXIT_OK
        captured = capsys.readouterr()
        assert "STATUS: OK" in captured.out
        assert "[watch]" in captured.err

    def test_cli_watch_once_drifted_tree(self, drifted_tree: Path, capsys):
        code = main(["watch", str(drifted_tree), "--once"])
        assert code == EXIT_DRIFT
        out = capsys.readouterr().out
        assert "STATUS: DRIFT DETECTED" in out or "layer" in out.lower()

    def test_cli_watch_missing_dir_exit_2(self, tmp_path: Path):
        code = main(["watch", str(tmp_path / "missing"), "--once"])
        assert code == EXIT_USAGE

    def test_cli_watch_bad_interval_exit_2(self, clean_tree: Path, capsys):
        code = main(["watch", str(clean_tree), "--interval", "0"])
        assert code == EXIT_USAGE
        assert "interval" in capsys.readouterr().err

    def test_cli_watch_parses_interval_default(self):
        from semantic_drift_detector.cli import build_parser

        args = build_parser().parse_args(["watch", "."])
        assert args.command == "watch"
        assert args.interval == 2.0
        args = build_parser().parse_args(["watch", ".", "--interval", "0.5"])
        assert args.interval == 0.5

    def test_cli_watch_once_json(self, clean_tree: Path, capsys):
        import json

        code = main(["watch", str(clean_tree), "--once", "--json"])
        assert code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["mode"] == "directory"
        assert "entropy" in payload


def test_real_sleep_signature_compatible(clean_tree: Path):
    # run_watch with default (real) sleep + once must not actually sleep.
    start = time.monotonic()
    events = run_watch(clean_tree, once=True)
    assert time.monotonic() - start < 2.0
    assert len(events) == 1
