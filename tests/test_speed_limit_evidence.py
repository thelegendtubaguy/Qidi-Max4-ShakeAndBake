from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from shakeandbake_analyze import SpeedLimitAnalysisOptions, analyze_speed_limit_capture
from shakeandbake_capture import (
    SPEED_LIMIT_COMMAND,
    SPEED_LIMIT_METADATA_KEY,
    make_invalid_speed_limit_capture,
    make_valid_speed_limit_capture,
    write_capture_artifact,
)
from tests.test_klipper_data_acquisition import FakeGCmd, FakePrinter, _null_context, load_plugin


class SpeedLimitEvidenceTests(unittest.TestCase):
    def test_speed_limit_command_registration_and_default_capture(self) -> None:
        printer = FakePrinter()
        _, plugin = load_plugin(printer)
        self.assertIn(SPEED_LIMIT_COMMAND, printer.gcode.commands)
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = FakeGCmd(
                OUTPUT_DIR=temp_dir,
                MAX_SPEED=100,
                SPEED_INCREMENT=100,
                ACCEL_MIN=5000,
                ACCEL_MAX=5000,
                ACCEL_INCREMENT=5000,
            )
            plugin.cmd_capture_speed_limits(cmd)
            capture = next(Path(temp_dir).glob("*.sbcapture.json"))
            data = json.loads(capture.read_text())

        self.assertEqual(data["command"], SPEED_LIMIT_COMMAND)
        evidence = data["metadata"][SPEED_LIMIT_METADATA_KEY]
        self.assertEqual([candidate["candidate_id"] for candidate in evidence["candidates"]], ["v100-a5000-001"])
        self.assertEqual({obs["axis"] for obs in evidence["trigger_observations"] if obs["phase"] == "endstop_baseline"}, {"x", "y"})
        self.assertEqual({m["metadata"].get("direction_angle") for m in data["measurements"] if m["metadata"].get("kind") == "speed_profile"}, {45.0, 135.0})
        self.assertIn("speed-limit plan", cmd.responses[0])
        self.assertIn("speed-limit capture complete", cmd.responses[-1])
        self.assertNotIn("max_velocity:", "\n".join(cmd.responses))
        self.assertNotIn("graph", "\n".join(cmd.responses).lower())

    def test_speed_limit_parameter_and_preflight_refusals(self) -> None:
        invalid_cases = [
            ({"AXIS": "Z"}, "Z-axis|CoreXY motion only"),
            ({"MAX_SPEED": 99999}, "MAX_SPEED exceeds"),
            ({"ACCEL_MAX": 999999}, "ACCEL_MAX exceeds"),
            ({"MAX_SPEED": 300, "SPEED_INCREMENT": 1, "MAX_CANDIDATES": 2}, "MAX_CANDIDATES"),
        ]
        for params, pattern in invalid_cases:
            with self.subTest(params=params):
                printer = FakePrinter()
                module, plugin = load_plugin(printer)
                with self.assertRaisesRegex(module.CommandError, pattern):
                    plugin.cmd_capture_speed_limits(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir(), **params))
                self.assertEqual(printer.resonance_tester.moves, [])

        unsafe = FakePrinter()
        unsafe.printing = True
        module, plugin = load_plugin(unsafe)
        with self.assertRaisesRegex(module.CommandError, "printing"):
            plugin.cmd_capture_speed_limits(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(unsafe.resonance_tester.moves, [])

        non_corexy = FakePrinter()
        module, plugin = load_plugin(non_corexy)
        plugin.max4_config = replace(plugin.max4_config, printer=replace(plugin.max4_config.printer, kinematics="cartesian"))
        with self.assertRaisesRegex(module.CommandError, "CoreXY"):
            plugin.cmd_capture_speed_limits(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir()))

    def test_speed_limit_state_restoration_on_failures(self) -> None:
        for failure in ("motion", "sampling", "writing", "validation"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                printer = FakePrinter()
                module, plugin = load_plugin(printer)
                if failure == "motion":
                    printer.resonance_tester.fail = True
                if failure == "sampling":
                    printer.lis2dw.fail = True
                if failure == "writing":
                    context = mock.patch.object(module, "write_capture_artifact", side_effect=RuntimeError("write failure"))
                elif failure == "validation":
                    diagnostic = SimpleNamespace(status_code="invalid_speed_limit_fixture")
                    validation = SimpleNamespace(diagnostics=(diagnostic,))
                    context = mock.patch.object(module, "write_capture_artifact", return_value=SimpleNamespace(ok=False, validation=validation))
                else:
                    context = _null_context()
                command = FakeGCmd(
                    OUTPUT_DIR=temp_dir,
                    MAX_SPEED=100,
                    SPEED_INCREMENT=100,
                    ACCEL_MIN=5000,
                    ACCEL_MAX=5000,
                    ACCEL_INCREMENT=5000,
                )
                with context:
                    if failure == "sampling":
                        plugin.cmd_capture_speed_limits(command)
                        capture = next(Path(temp_dir).glob("*.sbcapture.json"))
                        data = json.loads(capture.read_text())
                        codes = [item["code"] for item in data["metadata"][SPEED_LIMIT_METADATA_KEY]["diagnostics"]]
                        self.assertIn("shaper_phase_failed", codes)
                        self.assertIn("speed_profile_phase_failed", codes)
                    else:
                        with self.assertRaises(Exception):
                            plugin.cmd_capture_speed_limits(command)
                self.assertTrue(printer.input_shaper.state["enabled"])
                self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)
                self.assertGreaterEqual(printer.input_shaper.restores, 1)
                self.assertGreaterEqual(printer.toolhead.restores, 1)

    def test_analyzer_valid_capture_writes_observed_recommendations_and_speed_profile_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            capture = Path(temp_dir) / "speed-limit.sbcapture.json"
            write_result = write_capture_artifact(capture, make_valid_speed_limit_capture())
            self.assertTrue(write_result.ok)
            result = analyze_speed_limit_capture(capture, Path(temp_dir) / "out")
            output = Path(temp_dir) / "out"
            analysis = json.loads((output / "analysis-speed-limits.json").read_text())

            self.assertTrue(result.recommendations_available)
            self.assertEqual(analysis["motion_limits"]["observed_tested_ceilings"]["highest_passing_velocity"], 200.0)
            self.assertIn("max_velocity", analysis["recommendations"])
            self.assertIn("slicer_motion_speed", analysis["recommendations"])
            self.assertTrue(analysis["speed_profile"]["measurement_energy"])
            self.assertTrue(analysis["speed_profile"]["projection"]["per_speed"])
            self.assertTrue(analysis["speed_profile"]["avoid_bands"])
            self.assertTrue(analysis["speed_profile"]["preferred_ranges"])
            self.assertTrue((Path(result.output_dir) / "summary.txt").exists())
            self.assertTrue((Path(result.output_dir) / "speed-limits.proposed.cfg").exists())
            self.assertTrue((Path(result.output_dir) / "slicer-motion-speed.proposed.txt").exists())
            self.assertTrue((Path(result.output_dir) / "graphs" / "speed-angle-heatmap.svg").exists())

    def test_analyzer_invalid_artifacts_and_z_measurements_are_diagnostic(self) -> None:
        for kind, expected in (
            ("missing_baseline", "missing_baseline_evidence"),
            ("malformed_candidate", "malformed_candidate"),
            ("unavailable_trigger", "trigger_observation_unavailable"),
            ("closed_loop_fault", "closed_loop_unsafe"),
            ("incomplete_vibration", "missing_speed_profile_measurement"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp_dir:
                capture = Path(temp_dir) / f"{kind}.sbcapture.json"
                write_capture_artifact(capture, make_invalid_speed_limit_capture(kind))
                result = analyze_speed_limit_capture(capture, Path(temp_dir) / "out", SpeedLimitAnalysisOptions(graphs_enabled=False))
                analysis = json.loads((Path(temp_dir) / "out" / "analysis-speed-limits.json").read_text())
                codes = [diagnostic["code"] for diagnostic in analysis["diagnostics"]]
                self.assertIn(expected, codes)
                if kind in {"missing_baseline", "malformed_candidate", "closed_loop_fault"}:
                    self.assertTrue(result.blocked or codes)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = make_valid_speed_limit_capture()
            artifact.measurements.append(artifact.measurements[0].__class__("z_profile", "speed_profile", "lis2dw", artifact.measurements[0].samples, metadata={"kind": "speed_profile", "axis_label": "Z", "speed": 100, "direction_angle": 45}))
            capture = Path(temp_dir) / "z.sbcapture.json"
            write_capture_artifact(capture, artifact)
            analyze_speed_limit_capture(capture, Path(temp_dir) / "out", SpeedLimitAnalysisOptions(graphs_enabled=False))
            analysis = json.loads((Path(temp_dir) / "out" / "analysis-speed-limits.json").read_text())
        self.assertIn("z_speed_profile_ignored", [diagnostic["code"] for diagnostic in analysis["diagnostics"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            capture = Path(temp_dir) / "missing-shaper.sbcapture.json"
            write_capture_artifact(capture, make_valid_speed_limit_capture(include_shaper=False))
            result = analyze_speed_limit_capture(capture, Path(temp_dir) / "out", SpeedLimitAnalysisOptions(graphs_enabled=False))
            analysis = json.loads((Path(temp_dir) / "out" / "analysis-speed-limits.json").read_text())
        codes = [diagnostic["code"] for diagnostic in analysis["diagnostics"]]
        self.assertTrue(result.blocked)
        self.assertIn("recommendation_withheld_missing_shaper", codes)

    def test_graph_failure_keeps_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            capture = Path(temp_dir) / "speed-limit.sbcapture.json"
            write_capture_artifact(capture, make_valid_speed_limit_capture())
            output = Path(temp_dir) / "out"
            output.mkdir()
            (output / "graphs").write_text("not a directory")

            result = analyze_speed_limit_capture(capture, output)
            analysis = json.loads((output / "analysis-speed-limits.json").read_text())

        self.assertTrue(result.recommendations_available)
        self.assertIn("graph_generation_failed", [diagnostic["code"] for diagnostic in analysis["diagnostics"]])

    def test_speed_limits_cli_and_import_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            capture = Path(temp_dir) / "speed-limit.sbcapture.json"
            write_capture_artifact(capture, make_valid_speed_limit_capture())
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "shakeandbake_analyze",
                    "analyze",
                    "speed-limits",
                    str(capture),
                    "--output-dir",
                    str(Path(temp_dir) / "out"),
                    "--no-graphs",
                ],
                cwd=Path(__file__).parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((Path(temp_dir) / "out" / "analysis-speed-limits.json").exists())

        script = """
import sys
import shakeandbake_analyze.speed_limits
loaded = sorted(name for name in sys.modules if name == 'klipper' or name.startswith('klippy'))
print(loaded)
raise SystemExit(1 if loaded else 0)
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
