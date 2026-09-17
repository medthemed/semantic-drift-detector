"""Command-line interface for semantic-drift-detector."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from semantic_drift_detector.analyzer import analyze_directory
from semantic_drift_detector.batch import check_batch, resolve_roots
from semantic_drift_detector.diff_scan import analyze_diff
from semantic_drift_detector.errors import (
    DirectoryNotFoundError,
    DnaFileNotFoundError,
    DnaProfileError,
    SemanticDriftError,
    UnknownProfileError,
)
from semantic_drift_detector.profile import extract_dna, save_dna, snapshot_path_default
from semantic_drift_detector.report import (
    FORMAT_CHOICES,
    render_batch,
    render_result,
)

__version__ = "0.4.0"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdd",
        description="Detect architectural entropy and semantic drift in AI-assisted codebases.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"semantic-drift-detector {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # snapshot
    p_snap = sub.add_parser(
        "snapshot",
        help="Capture architectural DNA from a directory tree and write dna.toml",
    )
    p_snap.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root to snapshot (default: current directory)",
    )
    p_snap.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path for DNA profile (default: <root>/dna.toml)",
    )
    p_snap.add_argument(
        "--format",
        choices=("toml", "yaml", "json"),
        default="toml",
        help="DNA file format (default: toml)",
    )

    # check
    p_check = sub.add_parser(
        "check",
        help="Check a directory or diff against architectural DNA",
    )
    p_check.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Directory to check (ignored when --diff is used)",
    )
    p_check.add_argument(
        "--diff",
        default=None,
        metavar="PATCH",
        help="Path to a unified git diff file to analyze instead of a directory",
    )
    p_check.add_argument(
        "--dna",
        default=None,
        metavar="PATH",
        help="Path to dna.toml / dna.yaml (default: look under root, else infer)",
    )
    p_check.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help="Named profile from the DNA profiles section (default: base rules)",
    )
    p_check.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override entropy threshold (0-1)",
    )
    p_check.add_argument(
        "--format",
        choices=FORMAT_CHOICES,
        default="text",
        help="Report format: text, json, or sarif-lite (default: text)",
    )
    p_check.add_argument(
        "--json",
        action="store_true",
        help="Shorthand for --format json",
    )
    p_check.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include entropy components in text report",
    )

    # check-batch
    p_batch = sub.add_parser(
        "check-batch",
        help="Check multiple project roots (or a manifest of paths) in one run",
    )
    p_batch.add_argument(
        "roots",
        nargs="*",
        default=None,
        help="Project roots to check",
    )
    p_batch.add_argument(
        "--manifest",
        default=None,
        metavar="FILE",
        help="Manifest file with one project root per line (# comments allowed)",
    )
    p_batch.add_argument(
        "--dna",
        default=None,
        metavar="PATH",
        help="Explicit DNA profile applied to every root",
    )
    p_batch.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help="Named profile from the DNA profiles section",
    )
    p_batch.add_argument(
        "--format",
        choices=FORMAT_CHOICES,
        default="text",
        help="Report format: text, json, or sarif-lite (default: text)",
    )
    p_batch.add_argument(
        "--json",
        action="store_true",
        help="Shorthand for --format json",
    )

    # version subcommand (alias)
    sub.add_parser("version", help="Print version and exit")

    return parser


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: directory not found: {root}", file=sys.stderr)
        return EXIT_USAGE

    profile = extract_dna(root)
    if args.format == "toml":
        out = Path(args.output) if args.output else snapshot_path_default(root)
    elif args.format == "yaml":
        out = Path(args.output) if args.output else root / "dna.yaml"
    else:
        out = Path(args.output) if args.output else root / "dna.json"

    save_dna(profile, out)
    print(f"wrote DNA profile: {out}")
    print(f"  modules: {len(profile.modules)}")
    print(f"  edges:   {len(profile.edges)}")
    print(f"  layers:  {', '.join(layer.name for layer in profile.rules.layers) or '(none)'}")
    print(f"  threshold: {profile.rules.entropy_threshold}")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    dna_path = Path(args.dna) if args.dna else None

    try:
        if args.diff:
            diff_path = Path(args.diff)
            if not diff_path.is_file():
                print(f"error: diff not found: {diff_path}", file=sys.stderr)
                return EXIT_USAGE
            diff_text = diff_path.read_text(encoding="utf-8")
            result = analyze_diff(diff_text, dna_path=dna_path)
        else:
            root = Path(args.root).resolve()
            if not root.exists():
                print(f"error: directory not found: {root}", file=sys.stderr)
                return EXIT_USAGE
            result = analyze_directory(
                root, dna_path=dna_path, profile_name=args.profile
            )
    except UnknownProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (DnaFileNotFoundError, DnaProfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except DirectoryNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except SemanticDriftError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.threshold is not None:
        result.threshold = args.threshold

    fmt = "json" if args.json else args.format
    sys.stdout.write(render_result(result, fmt=fmt, verbose=args.verbose))

    return EXIT_DRIFT if result.breached else EXIT_OK


def cmd_check_batch(args: argparse.Namespace) -> int:
    try:
        roots = resolve_roots(args.roots or [], manifest=args.manifest)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not roots:
        print("error: no roots provided (pass roots or --manifest)", file=sys.stderr)
        return EXIT_USAGE

    dna_path = Path(args.dna) if args.dna else None
    report = check_batch(roots, dna_path=dna_path, profile_name=args.profile)

    fmt = "json" if args.json else args.format
    sys.stdout.write(render_batch(report, fmt=fmt))

    if report.any_error:
        return EXIT_USAGE
    if report.any_breached:
        return EXIT_DRIFT
    return EXIT_OK


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"semantic-drift-detector {__version__}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        return cmd_snapshot(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "check-batch":
        return cmd_check_batch(args)
    if args.command == "version":
        return cmd_version(args)

    parser.error(f"unknown command: {args.command}")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
