from __future__ import annotations

import argparse
import sys

from .belts import BeltAnalysisOptions, analyze_belt_capture
from .shaper import ShaperAnalysisOptions, analyze_shaper_capture
from .speed_limits import SpeedLimitAnalysisOptions, analyze_speed_limit_capture
from .static_frequency import StaticFrequencyAnalysisOptions, analyze_static_frequency_capture


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
    static = analyze_subcommands.add_parser("static-frequency")
    static.add_argument("capture_file")
    static.add_argument("--output-dir", required=True)
    static.add_argument("--segment-seconds", type=float, default=0.25)
    static.add_argument("--no-graphs", action="store_true")
    static.add_argument("--json-only", action="store_true")
    speed_limits = analyze_subcommands.add_parser("speed-limits")
    speed_limits.add_argument("capture_file")
    speed_limits.add_argument("--output-dir", required=True)
    speed_limits.add_argument("--frequency-min", type=float, default=5.0)
    speed_limits.add_argument("--frequency-max", type=float, default=140.0)
    speed_limits.add_argument("--angular-resolution", type=float, default=15.0)
    speed_limits.add_argument("--avoid-threshold", type=float, default=0.25)
    speed_limits.add_argument("--avoid-margin-speed", type=float, default=20.0)
    speed_limits.add_argument("--preferred-threshold", type=float, default=0.60)
    speed_limits.add_argument("--preferred-min-width", type=float, default=20.0)
    speed_limits.add_argument("--derate", type=float, default=0.85)
    speed_limits.add_argument("--no-graphs", action="store_true")
    speed_limits.add_argument("--json-only", action="store_true")
    speed_limits.add_argument("--summary-only", action="store_true")
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
    if args.command == "analyze" and args.analysis == "static-frequency":
        result = analyze_static_frequency_capture(
            args.capture_file,
            args.output_dir,
            StaticFrequencyAnalysisOptions(
                segment_seconds=args.segment_seconds,
                graphs_enabled=not args.no_graphs and not args.json_only,
                json_only=args.json_only,
            ),
        )
        return 0 if result.analysis_valid else 2
    if args.command == "analyze" and args.analysis == "speed-limits":
        result = analyze_speed_limit_capture(
            args.capture_file,
            args.output_dir,
            SpeedLimitAnalysisOptions(
                min_frequency_hz=args.frequency_min,
                max_frequency_hz=args.frequency_max,
                angular_resolution_degrees=args.angular_resolution,
                avoid_peak_relative_threshold=args.avoid_threshold,
                avoid_margin_speed=args.avoid_margin_speed,
                preferred_relative_threshold=args.preferred_threshold,
                preferred_min_width=args.preferred_min_width,
                derate=args.derate,
                graphs_enabled=not args.no_graphs and not args.json_only and not args.summary_only,
                json_only=args.json_only,
                summary_only=args.summary_only,
            ),
        )
        return 0 if result.recommendations_available else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
