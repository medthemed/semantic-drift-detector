# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-10-22

### Added
- `sdd watch <path>` polling watch mode (issue #14): re-checks a tree
  during local development without OS-specific file watchers.
  `--interval SECONDS` sets the poll interval (default 2.0).
- Tree fingerprinting: a `(path, mtime, size)` fingerprint of the tree's
  Python files (plus a root DNA file) drives re-checks — the drift check
  re-runs only when the fingerprint changes, and a report is printed only
  when the check result itself changes.
- Watch library API in the public exports: `directory_fingerprint`,
  `WatchEvent`, `watch_events` (generator, boundable via `max_polls` /
  `once`), and `run_watch` (callback helper used by the CLI).
- `sdd watch --once` single-pass mode for smoke checks / CI.
- Watch accepts the same `--dna` / `--profile` / `--threshold` /
  `--format` / `--json` / `--verbose` options as `sdd check`.
  Ctrl-C exits cleanly; the exit code reflects the last reported result
  (0 ok, 1 drift, 2 usage error).

### Fixed
- `sdd check` no longer replays the modules/edges stored in `dna.toml`
  when a DNA file is present at the project root. It now always rescans
  the current tree and uses the DNA file for rules only, so edits made
  after `sdd snapshot` — new files and new imports — are actually
  detected. (Previously, a forbidden import added after snapshotting
  still reported `STATUS: OK`.)
- Directory scans no longer silently return zero files when the project
  itself lives under a directory named `build`, `dist`, `venv`, `env`,
  etc. Skip-directory matching now only applies to directories inside
  the scanned tree, not to ancestors of the project root.

## [0.5.0] - 2026-09-25

### Added
- `--format json|sarif-lite|text` on `sdd check` and `sdd check-batch`
  (`--json` remains as shorthand for `--format json`).
- SARIF-lite renderer (`render_sarif_lite`) emitting a minimal SARIF 2.1.0
  document; entropy and threshold live in `runs[].properties`.
- JSON Schema files: `schemas/report.schema.json` and
  `schemas/batch-report.schema.json`.
- README: stdout contract for CI piping (stdout vs stderr, stable keys).
- Format-dispatch tests and schema shape checks.

## [0.4.0] - 2026-09-24

### Added
- `sdd check-batch` analyzes multiple project roots in one run.
- `--manifest FILE` reads roots from a text file (one path per line, `#`
  comments and blank lines skipped; relative paths resolve against the
  manifest directory).
- Pure-core batch API: `check_batch`, `check_one`, `load_manifest`,
  `BatchReport`, `BatchItemResult`. Safe to parallelize with a thread or
  process pool.
- Aggregate text/JSON batch report and exit codes (0 ok, 1 any drift,
  2 any load error / usage).
- Multi-tree fixture tests covering mixed clean/drifted roots, manifests,
  and concurrent `check_one` calls.

## [0.3.0] - 2026-09-23

### Added
- Named architecture profiles: `[profiles.<name>]` sections in `dna.toml` /
  `dna.yaml` / `dna.json` inherit base `[rules]` and override selected keys.
- `sdd check --profile <name>` selects a named profile (default: base rules).
- `select_profile(...)` / `merge_profile_overrides(...)` in the public API.
- `UnknownProfileError` when a requested profile is missing.
- README: profiles documentation and CLI examples.

## [0.2.0] - 2026-09-20

### Added
- Typed exception module (`semantic_drift_detector.errors`): `SemanticDriftError`,
  `DirectoryNotFoundError`, `DnaProfileError`, `DnaFileNotFoundError`,
  `InvalidDnaError`. Typed errors also subclass the historical builtins.
- Stable public `load_profile(...)` (same semantics as `load_dna`).
- Integration tests covering snapshot → reload → directory check on a tiny
  fixture tree, plus public `__all__` export checks.
- README: Python API section with exception hierarchy.

### Changed
- `analyze_directory` and DNA loaders raise typed exceptions; CLI maps them
  to exit code 2 with a clear stderr message.

## [0.1.1] - 2026-09-18

### Added
- `rules.exclude` path globs in `dna.toml` / `dna.yaml` / `dna.json` to skip
  generated code, migrations, and other non-architecture paths during DNA
  extraction and directory checks.
- README: CI status badge, copy-paste `dna.toml` example, and a GitHub Actions
  workflow snippet (full-tree + PR-diff checks).

## [0.1.0] - 2026-09-16

### Added
- Initial public MVP of semantic-drift-detector.
- Architectural DNA extraction: module dependency graph, layers, naming conventions, package boundaries.
- `dna.toml` / `dna.yaml` configuration for layers, forbidden edges, required patterns.
- Layering rule engine with import-edge classification.
- Entropy score computation (0–1) from violation mix and dependency density.
- Diff and directory-snapshot scanners.
- CLI: `sdd snapshot`, `sdd check`, `sdd version`.
- Human-readable and JSON report formats.
- Exit code 1 when entropy exceeds configured threshold.
- Pytest suite covering layering, naming, entropy bounds, clean-tree pass, and CLI exit codes.
