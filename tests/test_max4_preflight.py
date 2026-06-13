from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from shakeandbake_max4 import (
    AdapterSnapshot,
    MotionEnvelope,
    PreflightRequest,
    ResourceThresholds,
    TestPreflightAdapter,
    parse_max4_config,
    run_preflight,
)

FIXTURES = Path(__file__).parent / "fixtures" / "max4"


class Max4ConfigParsingTests(unittest.TestCase):
    def test_stock_config_parses_max4_sections(self) -> None:
        config = parse_max4_config(FIXTURES / "stock_printer.cfg")

        self.assertEqual(config.printer.kinematics, "corexy")
        self.assertEqual(config.printer.max_velocity, 600.0)
        self.assertEqual(config.printer.max_accel, 20000.0)
        self.assertEqual(config.printer.max_z_velocity, 20.0)
        self.assertEqual(config.printer.max_z_accel, 500.0)
        self.assertEqual(config.printer.square_corner_velocity, 5.0)
        self.assertEqual(config.resonance_tester.accel_chip, "lis2dw")
        self.assertEqual(config.resonance_tester.accel_per_hz, 75.0)
        self.assertEqual(config.resonance_tester.max_smoothing, 0.12)
        self.assertEqual(config.resonance_tester.primary_probe_point, (195.0, 195.0, 10.0))
        self.assertEqual(config.lis2dw.axes_map, "y,z,-x")
        self.assertEqual(config.lis2dw.accelerometer_identity, "lis2dw")
        self.assertEqual(config.input_shaper.shaper_type_x, "mzv")
        self.assertEqual(config.input_shaper.shaper_freq_y, 39.2)

    def test_closed_loop_xy_metadata_is_parsed_without_standard_tmc_sections(self) -> None:
        config = parse_max4_config(FIXTURES / "stock_printer.cfg")

        self.assertNotIn("tmc2209 stepper_x", config.raw_sections)
        self.assertNotIn("tmc2209 stepper_y", config.raw_sections)
        self.assertEqual(config.motors["x"].section, "closed_loop x")
        self.assertEqual(config.motors["x"].run_current, 1.20)
        self.assertEqual(config.motors["x"].hold_current, 0.60)
        self.assertEqual(config.motors["x"].home_current, 0.80)
        self.assertEqual(config.motors["x"].microsteps, 16)
        self.assertEqual(config.motors["y"].run_current, 1.25)
        self.assertEqual(config.motors["y"].hold_current, 0.65)
        self.assertEqual(config.motors["y"].home_current, 0.85)
        self.assertEqual(config.motors["y"].microsteps, 16)


class Max4PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = parse_max4_config(FIXTURES / "stock_printer.cfg")
        self.ready_state = AdapterSnapshot(
            printer_ready=True,
            printing=False,
            paused=False,
            virtual_sd_active=False,
            homing=False,
            accelerometer_available=True,
            host_load=0.4,
            free_memory_mb=2048,
            free_disk_mb=4096,
            fan_state={"part": 0.0},
            heater_state={"extruder": {"target": 0.0, "temperature": 26.0}},
            chamber_state={"temperature": 27.0},
            input_shaper_state={"shaper_type_x": "mzv"},
            velocity_limit_state={"max_velocity": 600.0},
            toolhead_position=(195.0, 195.0, 10.0),
        )

    def run_preflight_with(self, state: AdapterSnapshot, request: PreflightRequest | None = None):
        return run_preflight(request or PreflightRequest(), self.config, TestPreflightAdapter(state))

    def test_ready_printer_passes_with_snapshots(self) -> None:
        result = self.run_preflight_with(self.ready_state)

        self.assertTrue(result.ready)
        self.assertEqual(result.blocking_findings, ())
        self.assertEqual(result.supported_axes, ("x", "y"))
        self.assertEqual(result.state.probe_point, (195.0, 195.0, 10.0))
        self.assertEqual(result.state.accelerometer_identity, "lis2dw")
        self.assertEqual(result.state.axes_map, "y,z,-x")
        self.assertEqual(result.state.fan_state["part"], 0.0)
        self.assertEqual(result.state.heater_state["extruder"]["temperature"], 26.0)
        self.assertEqual(result.state.chamber_state["temperature"], 27.0)

    def test_unsafe_states_block_acquisition(self) -> None:
        cases = [
            (AdapterSnapshot(**{**self.ready_state.__dict__, "printer_ready": False}), "printer_not_ready"),
            (AdapterSnapshot(**{**self.ready_state.__dict__, "printing": True}), "printing"),
            (AdapterSnapshot(**{**self.ready_state.__dict__, "paused": True}), "paused"),
            (AdapterSnapshot(**{**self.ready_state.__dict__, "virtual_sd_active": True}), "virtual_sd_active"),
            (AdapterSnapshot(**{**self.ready_state.__dict__, "homing": True}), "homing"),
            (
                AdapterSnapshot(**{**self.ready_state.__dict__, "accelerometer_available": False}),
                "accelerometer_unavailable",
            ),
        ]
        for state, code in cases:
            with self.subTest(code=code):
                result = self.run_preflight_with(state)
                self.assertFalse(result.ready)
                self.assertIn(code, [finding.code for finding in result.blocking_findings])

    def test_motion_envelope_inside_bounds_passes(self) -> None:
        request = PreflightRequest(motion_envelope=MotionEnvelope(100, 220, 100, 220), safety_margin_mm=5)

        result = self.run_preflight_with(self.ready_state, request)

        self.assertTrue(result.ready)
        self.assertNotIn("motion_envelope_out_of_bounds", [finding.code for finding in result.findings])

    def test_motion_envelope_out_of_bounds_blocks(self) -> None:
        request = PreflightRequest(motion_envelope=MotionEnvelope(1, 220, 100, 220), safety_margin_mm=5)

        result = self.run_preflight_with(self.ready_state, request)

        self.assertFalse(result.ready)
        self.assertEqual(result.blocking_findings[0].code, "motion_envelope_out_of_bounds")

    def test_low_resources_emit_warnings_without_blocking(self) -> None:
        state = AdapterSnapshot(
            **{
                **self.ready_state.__dict__,
                "host_load": 6.0,
                "free_memory_mb": 128.0,
                "free_disk_mb": 128.0,
            }
        )
        request = PreflightRequest(
            resource_thresholds=ResourceThresholds(max_load=4.0, min_free_memory_mb=256, min_free_disk_mb=512)
        )

        result = self.run_preflight_with(state, request)

        self.assertTrue(result.ready)
        self.assertEqual(
            [finding.code for finding in result.warnings],
            ["host_load_warning", "free_memory_warning", "free_disk_warning"],
        )

    def test_supported_axes_are_xy_and_z_request_blocks(self) -> None:
        result = self.run_preflight_with(self.ready_state, PreflightRequest(axes=("z",)))

        self.assertEqual(result.supported_axes, ("x", "y"))
        self.assertFalse(result.ready)
        self.assertEqual(result.blocking_findings[0].code, "z_axis_unsupported")

    def test_package_import_does_not_import_klipper(self) -> None:
        script = """
import sys
import shakeandbake_max4
loaded = sorted(name for name in sys.modules if name == 'klipper' or name.startswith('klippy'))
print(loaded)
raise SystemExit(1 if loaded else 0)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
