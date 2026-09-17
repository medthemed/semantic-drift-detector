# Architecture

## Problem

AI coding agents optimize for *local* correctness. Applied repeatedly, they
follow the nearest existing pattern and gradually erode *global* architectural
intent — semantic drift / architectural entropy. Examples:

- `domain` modules importing `adapters` or `infrastructure`
- services calling into HTTP handlers
- new top-level packages that bypass allowed boundaries
- naming conventions decaying (`userRepo.py`, `snake_case` classes)

`semantic-drift-detector` makes this drift visible and gateable.

## High-level flow

```
                ┌─────────────┐
   directory ──►│  parser.py  │──► ModuleInfo[] + ImportEdge[]
                └─────────────┘
                        │
                        ▼
                ┌─────────────┐     dna.toml / dna.yaml
                │ profile.py  │◄────────────────────────
                └─────────────┘
                        │ DNAProfile (modules, edges, rules)
                        ▼
                ┌─────────────┐
                │  rules.py   │──► Violation[]
                └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │ entropy.py  │──► EntropyScore (0–1)
                └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │  report.py  │──► text | JSON
                └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │   cli.py    │──► exit 0 | 1 | 2
                └─────────────┘
```

Diff mode replaces the directory walk with `diff_scan.py`, which reconstructs
added Python lines from a unified diff and runs the same rule/entropy pipeline.

## Modules

| Module | Responsibility |
|--------|----------------|
| `types.py` | Frozen dataclasses: `DNAProfile`, `DNARules`, `ImportEdge`, `Violation`, `EntropyScore`, `CheckResult` |
| `parser.py` | Walk tree, `ast.parse` sources, extract imports/classes/functions, path→dotted module |
| `profile.py` | `extract_dna` / `load_dna` / `save_dna`; default layer inference; TOML & minimal YAML IO |
| `rules.py` | Layering, naming, required-pattern evaluation |
| `entropy.py` | Weighted 0–1 entropy from violations + graph shape |
| `diff_scan.py` | Unified-diff parsing and partial-source analysis |
| `analyzer.py` | Directory analysis orchestration |
| `report.py` | Human text + JSON rendering |
| `cli.py` | `sdd snapshot` / `sdd check` / `sdd version` |

## Design decisions

### Layer membership is prefix-based

A layer is a set of dotted prefixes (`myapp.domain`, `domain`, …). Classification
uses longest-prefix resolution so `myapp.adapters.payment.ChargeService` resolves
to the `adapters` layer even when the class is not a module in the graph.

### Rules are data, not code

Everything gateable lives in `dna.toml`: layers, forbidden edges, naming regexes,
required path globs, entropy threshold. That keeps the analyzer generic and makes
DNA profiles reviewable artifacts.

### Inference before configuration

`sdd check` on a tree without `dna.toml` infers clean-architecture defaults from
common package names (`domain`, `application`, `adapters`, `interfaces`, …).
This lowers the adoption barrier; teams then pin a snapshot with `sdd snapshot`.

### Diff analysis is additive-only

Only `+` lines are analyzed. Removed lines cannot introduce new violations.
Partial snippets that fail `ast.parse` fall back to regex import extraction so
CI does not false-negative on incomplete hunks.

### Entropy is explainable

The score is a linear combination of four named components, each saturating at a
documented healthy ceiling. Reports can show components with `--verbose` so a
threshold breach is actionable, not mysterious.

### Zero third-party runtime deps

Stdlib `ast`, `tomllib`, `argparse`, `re`, `pathlib` cover the MVP. A small YAML
subset reader/writer avoids PyYAML. `pytest` is the only test dependency.

## Exit-code contract

- `0` — entropy ≤ threshold **and** no `error`-severity violations
- `1` — drift (threshold breach or errors)
- `2` — usage / IO error

`warning`-severity findings (naming) do not fail the gate by themselves; they
raise entropy and are reported for review.

## Extension points

- Additional `NamingRule.kind` values (`function` already supported)
- `check_boundaries` for cross-root first-party packages (hook present, currently conservative)
- Baseline / ratchet mode (store prior entropy, fail only on regression)
- Plugin hooks for language-specific parsers (currently Python-only)
