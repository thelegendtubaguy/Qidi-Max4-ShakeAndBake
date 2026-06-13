from __future__ import annotations

import argparse
import sys

from .belts import BeltAnalysisOptions, analyze_belt_capture
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
    belts = analyze_subcommands.add_parser("belts")
    belts.add_argument("capture_file")
    belts.add_argument("--output-dir", required=True)
    belts.add_argument("--peak-pairing-threshold-hz", type=float, default=5.0)
    belts.add_argument("--peak-relative-threshold", type=float, default=0.25)
    belts.add_argument("--peak-absolute-threshold", type=float, default=1e-12)
    belts.add_argument("--no-graphs", action="store_true")
    belts.add_argument("--json-only", action="store_true")
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
    if args.command == "analyze" and args.analysis == "belts":
        result = analyze_belt_capture(
            args.capture_file,
            args.output_dir,
            BeltAnalysisOptions(
                peak_pairing_threshold_hz=args.peak_pairing_threshold_hz,
                peak_relative_threshold=args.peak_relative_threshold,
                peak_absolute_threshold=args.peak_absolute_threshold,
                graphs_enabled=not args.no_graphs and not args.json_only,
                json_only=args.json_only,
            ),
        )
        return 0 if result.comparison_valid else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
