# semantic-drift-detector

Catch architectural entropy before it compounds.

AI coding agents are excellent at *local* pattern-matching. Over many patches they
quietly erode *global* architectural intent: domain code starts importing adapters,
services reach into the UI, package boundaries blur. This tool captures an
**architectural DNA** profile from a codebase and scores structural drift on every
diff.

## Features

- **DNA snapshot** — module dependency graph, layer membership, naming rules, package roots
- **Configurable rules** — `dna.toml` / `dna.yaml` with layers, forbidden edges, required patterns
- **Entropy score (0–1)** — layer violations, naming drift, fan-out pressure, edge density
- **Diff or directory checks** — analyze a full tree or a single `git diff`
- **CI-friendly** — exit code `1` when entropy exceeds threshold; JSON or human reports
- **Zero runtime deps** — Python 3.11+ stdlib only (`pytest` for tests)

## Install

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
# Capture DNA from a project
sdd snapshot /path/to/project

# Check a directory (uses dna.toml if present, otherwise infers rules)
sdd check /path/to/project

# Check a git diff (e.g. in CI)
git diff main...HEAD > patch.diff
sdd check --diff patch.diff --dna /path/to/project/dna.toml

# Machine-readable report
sdd check /path/to/project --json

# Fail harder / softer
sdd check /path/to/project --threshold 0.15
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | OK — entropy at or below threshold, no error-level violations |
| 1 | Drift detected — threshold breach or error-level violations |
| 2 | Usage error |

## Example report

```
semantic-drift-detector report
========================================
mode:         directory
dna:          /proj/dna.toml
files:        42
threshold:    0.25
entropy:      0.3120 [######------------]
errors:       2
warnings:     1

violations (3):
  ✗ (error) app.domain.order (domain) imports app.adapters.payment (adapters): domain must not depend on adapters
  ✗ (error) app.domain.billing (domain) imports app.interfaces.api (interfaces): domain must not depend on delivery mechanisms
  ! (warning) module 'BadName' violates /^[a-z_][a-z0-9_]*$/

STATUS: DRIFT DETECTED (exit 1)
```

## Configuration (`dna.toml`)

```toml
[rules]
entropy_threshold = 0.25
allowed_roots = ["myapp"]
required_patterns = ["**/domain/**", "**/adapters/**"]

[[rules.layers]]
name = "domain"
prefixes = ["myapp.domain"]

[[rules.layers]]
name = "adapters"
prefixes = ["myapp.adapters"]

[[rules.forbidden_edges]]
from_layer = "domain"
to_layer = "adapters"
reason = "domain must not depend on adapters"

[[rules.naming]]
kind = "module"
pattern = "^[a-z_][a-z0-9_]*$"
message = "modules must be snake_case"
```

`sdd snapshot` writes a complete profile including the discovered module graph.
Hand-edit the `rules` section; leave `[[modules]]` / `[[edges]]` alone (they are
regenerated on the next snapshot).

## How entropy works

Entropy is a weighted sum of four normalized components (each 0–1):

| Component | Weight | Signal |
|-----------|--------|--------|
| layer | 0.45 | forbidden layer edges + required-pattern misses |
| naming | 0.20 | module/class naming convention failures |
| fanout | 0.20 | average unique outgoing imports per module |
| density | 0.15 | total import edges / modules |

The score is clamped to `[0, 1]`. Threshold defaults to `0.25`.

## Python API

```python
from semantic_drift_detector import extract_dna, analyze_directory, analyze_diff, save_dna

dna = extract_dna("src/")
save_dna(dna, "dna.toml")

result = analyze_directory(".", dna_path="dna.toml")
print(result.entropy.value, result.breached)

result = analyze_diff(open("patch.diff").read(), dna_path="dna.toml")
```

## Development

```bash
pip install -e ".[dev]"
pytest
pytest --cov=semantic_drift_detector
```

## License

MIT — see [LICENSE](LICENSE).
