# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
