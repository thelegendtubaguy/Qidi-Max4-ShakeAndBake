from __future__ import annotations

import argparse
import sys

from .shaper import ShaperAnalysisOptions, analyze_shaper_capture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shakeandbake")
    subcommands = parser.add_subparsers(dest="command", required=True)
    analyze = subcommands.add_parser("analyze")
    analyze_subcommands = analyze.add_subparsers(dest="analysis", required=True)
    shaper = analyze_subcommands.add_parser("shaper")
    shaper.add_argument("capture_file")
    shaper.add_argument("--output-dir", required=True)
    shaper.add_argument("--max-smoothing", type=float, default=0.35)
    shaper.add_argument("--residual-vibration-threshold", type=float, default=0.25)
    shaper.add_argument("--no-graphs", action="store_true")
    shaper.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze" and args.analysis == "shaper":
        result = analyze_shaper_capture(
            args.capture_file,
            args.output_dir,
            ShaperAnalysisOptions(
                max_smoothing=args.max_smoothing,
                residual_vibration_threshold=args.residual_vibration_threshold,
                graphs_enabled=not args.no_graphs and not args.json_only,
                json_only=args.json_only,
            ),
        )
        return 0 if result.recommendations_available else 2 if result.blocked else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
