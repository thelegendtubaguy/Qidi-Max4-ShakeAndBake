from __future__ import annotations

import importlib
import json
from dataclasses import replace
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shakeandbake_max4 import parse_max4_config

FIXTURES = Path(__file__).parent / "fixtures" / "max4"


class FakeGCode:
    def __init__(self) -> None:
        self.commands = {}
        self.responses = []

    def register_command(self, name, callback) -> None:
        self.commands[name] = callback

    def respond_info(self, message: str) -> None:
        self.responses.append(message)


class FakeGCmd:
    def __init__(self, **params) -> None:
        self.params = {key.upper(): value for key, value in params.items()}
        self.responses = []

    def get(self, key: str, default=None):
        return self.params.get(key.upper(), default)

    def get_float(self, key: str, default=None, above=None):
        value = float(self.params.get(key.upper(), default))
        if above is not None and value <= above:
            raise ValueError(f"{key} must be greater than {above}")
        return value

    def respond_info(self, message: str) -> None:
        self.responses.append(message)


class FakeToolhead:
    def __init__(self) -> None:
        self.velocity_limits = {"max_velocity": 600.0, "max_accel": 20000.0, "square_corner_velocity": 5.0}
        self.restores = 0
        self.fail_restore = False

    def snapshot_velocity_limits(self):
        return dict(self.velocity_limits)

    def update_velocity_limits(self, **kwargs) -> None:
        self.velocity_limits.update({key: value for key, value in kwargs.items() if value is not None})

    def restore_velocity_limits(self, snapshot) -> None:
        if self.fail_restore:
            raise RuntimeError("velocity restore failed")
        self.restores += 1
        self.velocity_limits = dict(snapshot)

    def get_position(self):
        return (195.0, 195.0, 10.0)


class FakeInputShaper:
    def __init__(self) -> None:
        self.state = {"enabled": True, "shaper_type_x": "mzv", "shaper_type_y": "ei"}
        self.restores = 0
        self.fail_restore = False

    def snapshot(self):
        return dict(self.state)

    def disable(self) -> None:
        self.state["enabled"] = False

    def restore(self, snapshot) -> None:
        if self.fail_restore:
            raise RuntimeError("input shaper restore failed")
        self.restores += 1
        self.state = dict(snapshot)


class FakeAccelerometer:
    def __init__(self) -> None:
        self.fail = False
        self.samples_by_axis = {
            "x": [[0.000, 0.10, 0.02, 9.80], [0.001, 0.15, 0.03, 9.81], [0.002, 0.09, 0.04, 9.79]],
            "y": [[0.000, 0.01, 0.10, 9.80], [0.001, 0.03, 0.15, 9.81], [0.002, 0.02, 0.09, 9.79]],
            "a": [[0.000, 0.11, -0.10, 9.80], [0.001, 0.16, -0.15, 9.81], [0.002, 0.10, -0.09, 9.79]],
            "b": [[0.000, 0.11, 0.10, 9.80], [0.001, 0.16, 0.15, 9.81], [0.002, 0.10, 0.09, 9.79]],
        }

    def acquire_samples(self, axis, params):
        if self.fail:
            raise RuntimeError("sample failure")
        return self.samples_by_axis[axis]


class FakeResonanceTester:
    def __init__(self) -> None:
        self.moves = []
        self.fail = False
        self.fail_path = None

    def run_axis(self, axis, params) -> None:
        if self.fail or axis.upper() == self.fail_path:
            raise RuntimeError("motion failure")
        self.moves.append((axis, params))


class FakePrinter:
    def __init__(self) -> None:
        self.gcode = FakeGCode()
        self.toolhead = FakeToolhead()
        self.input_shaper = FakeInputShaper()
        self.resonance_tester = FakeResonanceTester()
        self.lis2dw = FakeAccelerometer()
        self.virtual_sdcard = type("VirtualSD", (), {"is_active": lambda self: False})()
        self.pause_resume = type("PauseResume", (), {"is_paused": lambda self: False})()
        self.ready = True
        self.printing = False
        self.paused = False
        self.virtual_sd_active = False
        self.homing = False
        self.host_load = 0.2
        self.free_memory_mb = 2048.0
        self.free_disk_mb = 4096.0
        self.fan_state = {"part": 0.0}
        self.heater_state = {"extruder": {"temperature": 25.0, "target": 0.0}}
        self.chamber_state = {"temperature": 27.0}

    def is_ready(self) -> bool:
        return self.ready

    def lookup_object(self, name, default=None):
        if hasattr(self, name):
            return getattr(self, name)
        if default is not None:
            return default
        raise KeyError(name)


class FakeConfig:
    def __init__(self, printer: FakePrinter) -> None:
        self.printer = printer
        self.max4_config = parse_max4_config(FIXTURES / "stock_printer.cfg")

    def get_printer(self) -> FakePrinter:
        return self.printer


def load_plugin(printer: FakePrinter):
    module = importlib.import_module("klippy.extras.shakeandbake")
    plugin = module.load_config(FakeConfig(printer))
    return module, plugin


class KlipperDataAcquisitionTests(unittest.TestCase):
    def test_command_registration(self) -> None:
        printer = FakePrinter()
        load_plugin(printer)

        self.assertIn("SHAKEANDBAKE_PREFLIGHT", printer.gcode.commands)
        self.assertIn("SHAKEANDBAKE_CAPTURE_SHAPER", printer.gcode.commands)
        self.assertIn("SHAKEANDBAKE_CAPTURE_BELTS", printer.gcode.commands)
        self.assertIn("SHAKEANDBAKE_EXCITE", printer.gcode.commands)

    def test_plugin_import_does_not_import_heavy_or_analyzer_modules(self) -> None:
        script = """
import sys
import klippy.extras.shakeandbake
forbidden = ('numpy', 'scipy', 'matplotlib', 'zstandard', 'shakeandbake_analyzer')
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
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

    def test_preflight_output_ready_and_blocking(self) -> None:
        printer = FakePrinter()
        _, plugin = load_plugin(printer)
        ready_cmd = FakeGCmd()

        plugin.cmd_preflight(ready_cmd)

        self.assertIn("Shake&Bake preflight: ready", ready_cmd.responses[0])
        self.assertIn("supported_axes=X,Y", ready_cmd.responses[0])
        self.assertIn("accelerometer=lis2dw", ready_cmd.responses[0])

        printer.printing = True
        blocking_cmd = FakeGCmd()
        plugin.cmd_preflight(blocking_cmd)

        self.assertIn("Shake&Bake preflight: not-ready", blocking_cmd.responses[0])
        self.assertIn("blocking=printing", blocking_cmd.responses[0])

    def test_capture_refuses_unsafe_states_and_z_axis_before_motion(self) -> None:
        unsafe_states = [
            ("printing", "printing"),
            ("paused", "paused"),
            ("virtual_sd_active", "virtual_sd_active"),
            ("homing", "homing"),
            ("ready", "printer_not_ready"),
        ]
        for attr, code in unsafe_states:
            with self.subTest(attr=attr):
                printer = FakePrinter()
                if attr == "ready":
                    printer.ready = False
                else:
                    setattr(printer, attr, True)
                module, plugin = load_plugin(printer)

                with self.assertRaisesRegex(module.CommandError, code):
                    plugin.cmd_capture_shaper(FakeGCmd(AXIS="X", OUTPUT_DIR=tempfile.gettempdir()))
                self.assertEqual(printer.resonance_tester.moves, [])

        printer = FakePrinter()
        module, plugin = load_plugin(printer)
        with self.assertRaisesRegex(module.CommandError, "supports AXIS=X, AXIS=Y, or AXIS=ALL"):
            plugin.cmd_capture_shaper(FakeGCmd(AXIS="Z", OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

    def test_capture_refuses_missing_accelerometer(self) -> None:
        printer = FakePrinter()
        printer.lis2dw = None
        module, plugin = load_plugin(printer)

        with self.assertRaisesRegex(module.CommandError, "accelerometer_unavailable|feature detection"):
            plugin.cmd_capture_shaper(FakeGCmd(AXIS="X", OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

    def test_successful_axis_x_y_and_all_capture_artifacts(self) -> None:
        cases = [("X", ["x_shaper"]), ("Y", ["y_shaper"]), ("ALL", ["x_shaper", "y_shaper"])]
        for axis, names in cases:
            with self.subTest(axis=axis), tempfile.TemporaryDirectory() as temp_dir:
                printer = FakePrinter()
                _, plugin = load_plugin(printer)
                cmd = FakeGCmd(AXIS=axis, OUTPUT_DIR=temp_dir)

                plugin.cmd_capture_shaper(cmd)

                captures = list(Path(temp_dir).glob("*.sbcapture.json"))
                self.assertEqual(len(captures), 1)
                data = json.loads(captures[0].read_text())
                self.assertEqual([measurement["name"] for measurement in data["measurements"]], names)
                self.assertEqual(data["command"], "SHAKEANDBAKE_CAPTURE_SHAPER")
                self.assertIn("input_shaper_state", data["metadata"])
                self.assertIn("velocity_limit_state", data["metadata"])
                self.assertTrue(data["metadata"]["restoration_status"]["ok"])
                self.assertIn("capture complete", cmd.responses[0])
                self.assertNotIn("shaper_type", cmd.responses[0])
                self.assertNotIn("printer.cfg", cmd.responses[0])
                self.assertTrue(printer.input_shaper.state["enabled"])
                self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)

    def test_forced_motion_sampling_and_writing_exceptions_restore_state(self) -> None:
        cases = ["motion", "sampling", "writing"]
        for failure in cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                printer = FakePrinter()
                module, plugin = load_plugin(printer)
                if failure == "motion":
                    printer.resonance_tester.fail = True
                if failure == "sampling":
                    printer.lis2dw.fail = True

                patcher = mock.patch.object(module, "write_capture_artifact", side_effect=RuntimeError("write failure"))
                context = patcher if failure == "writing" else _null_context()
                with context:
                    with self.assertRaises(Exception):
                        plugin.cmd_capture_shaper(FakeGCmd(AXIS="X", OUTPUT_DIR=temp_dir))

                self.assertTrue(printer.input_shaper.state["enabled"])
                self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)
                self.assertGreaterEqual(printer.input_shaper.restores, 1)
                self.assertGreaterEqual(printer.toolhead.restores, 1)

    def test_belt_capture_parameter_parsing_and_direction_metadata(self) -> None:
        printer = FakePrinter()
        _, plugin = load_plugin(printer)
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = FakeGCmd(
                FREQ_START=12,
                FREQ_END=88,
                HZ_PER_SEC=2,
                ACCEL_PER_HZ=66,
                TRAVEL_SPEED=140,
                ACCEL_CHIP="lis2dw",
                OUTPUT_DIR=temp_dir,
            )

            plugin.cmd_capture_belts(cmd)

            capture = next(Path(temp_dir).glob("*.sbcapture.json"))
            data = json.loads(capture.read_text())

        self.assertEqual(data["command"], "SHAKEANDBAKE_CAPTURE_BELTS")
        self.assertEqual([measurement["name"] for measurement in data["measurements"]], ["belt_a", "belt_b"])
        self.assertEqual(data["measurements"][0]["metadata"]["path_label"], "A")
        self.assertEqual(data["measurements"][0]["metadata"]["direction_vector"], [1, -1, 0])
        self.assertEqual(data["measurements"][1]["metadata"]["path_label"], "B")
        self.assertEqual(data["measurements"][1]["metadata"]["direction_vector"], [1, 1, 0])
        for measurement in data["measurements"]:
            self.assertEqual(measurement["metadata"]["freq_start"], 12.0)
            self.assertEqual(measurement["metadata"]["freq_end"], 88.0)
            self.assertEqual(measurement["metadata"]["hz_per_sec"], 2.0)
            self.assertEqual(measurement["metadata"]["accel_per_hz"], 66.0)
            self.assertEqual(measurement["metadata"]["travel_speed"], 140.0)
        self.assertIn("belt capture complete", cmd.responses[0])
        self.assertNotIn("PSD", cmd.responses[0])
        self.assertNotIn("similarity", cmd.responses[0])
        self.assertNotIn("graph", cmd.responses[0])
        self.assertNotIn("health", cmd.responses[0])

    def test_belt_capture_refuses_unsafe_states_out_of_bounds_and_axis_semantics(self) -> None:
        unsafe_states = [
            ("printing", "printing"),
            ("paused", "paused"),
            ("virtual_sd_active", "virtual_sd_active"),
            ("homing", "homing"),
            ("ready", "printer_not_ready"),
        ]
        for attr, code in unsafe_states:
            with self.subTest(attr=attr):
                printer = FakePrinter()
                if attr == "ready":
                    printer.ready = False
                else:
                    setattr(printer, attr, True)
                module, plugin = load_plugin(printer)

                with self.assertRaisesRegex(module.CommandError, code):
                    plugin.cmd_capture_belts(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir()))
                self.assertEqual(printer.resonance_tester.moves, [])

        printer = FakePrinter()
        module, plugin = load_plugin(printer)
        with self.assertRaisesRegex(module.CommandError, "AXIS parameters are unsupported"):
            plugin.cmd_capture_belts(FakeGCmd(AXIS="Z", OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

        printer = FakePrinter()
        module, plugin = load_plugin(printer)
        plugin.max4_config = replace(plugin.max4_config, xy_bounds=(0.0, 100.0, 0.0, 100.0))
        with self.assertRaisesRegex(module.CommandError, "motion_envelope_out_of_bounds"):
            plugin.cmd_capture_belts(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

        printer = FakePrinter()
        module, plugin = load_plugin(printer)
        plugin.max4_config = replace(plugin.max4_config, printer=replace(plugin.max4_config.printer, kinematics="cartesian"))
        with self.assertRaisesRegex(module.CommandError, "CoreXY"):
            plugin.cmd_capture_belts(FakeGCmd(OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

    def test_successful_belt_capture_artifact_creation(self) -> None:
        printer = FakePrinter()
        _, plugin = load_plugin(printer)
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = FakeGCmd(OUTPUT_DIR=temp_dir)
            plugin.cmd_capture_belts(cmd)
            capture = next(Path(temp_dir).glob("*.sbcapture.json"))
            data = json.loads(capture.read_text())

        self.assertEqual(data["command"], "SHAKEANDBAKE_CAPTURE_BELTS")
        self.assertEqual([measurement["metadata"]["path_label"] for measurement in data["measurements"]], ["A", "B"])
        self.assertIn("planned_motion_envelope", data["metadata"])
        self.assertIn("probe_point", data["metadata"])
        self.assertIn("axes_map", data["metadata"])
        self.assertIn("input_shaper_state", data["metadata"])
        self.assertIn("velocity_limit_state", data["metadata"])
        self.assertTrue(data["metadata"]["restoration_status"]["ok"])
        self.assertTrue(printer.input_shaper.state["enabled"])
        self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)

    def test_forced_belt_capture_and_writing_failures_restore_state(self) -> None:
        cases = ["a_motion", "b_motion", "writing"]
        for failure in cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                printer = FakePrinter()
                module, plugin = load_plugin(printer)
                if failure == "a_motion":
                    printer.resonance_tester.fail_path = "A"
                if failure == "b_motion":
                    printer.resonance_tester.fail_path = "B"

                patcher = mock.patch.object(module, "write_capture_artifact", side_effect=RuntimeError("write failure"))
                context = patcher if failure == "writing" else _null_context()
                with context:
                    with self.assertRaises(Exception):
                        plugin.cmd_capture_belts(FakeGCmd(OUTPUT_DIR=temp_dir))

                self.assertTrue(printer.input_shaper.state["enabled"])
                self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)
                self.assertGreaterEqual(printer.input_shaper.restores, 1)
                self.assertGreaterEqual(printer.toolhead.restores, 1)

    def test_static_frequency_parameter_validation_and_axis_mapping(self) -> None:
        printer = FakePrinter()
        module, plugin = load_plugin(printer)
        with self.assertRaisesRegex(module.CommandError, "FREQUENCY"):
            plugin.cmd_excite(FakeGCmd(AXIS="X", DURATION=1, OUTPUT_DIR=tempfile.gettempdir()))
        with self.assertRaisesRegex(module.CommandError, "DURATION"):
            plugin.cmd_excite(FakeGCmd(AXIS="X", FREQUENCY=40, OUTPUT_DIR=tempfile.gettempdir()))
        with self.assertRaisesRegex(module.CommandError, "supports AXIS=X"):
            plugin.cmd_excite(FakeGCmd(AXIS="Z", FREQUENCY=40, DURATION=1, OUTPUT_DIR=tempfile.gettempdir()))
        for axis, vector in {"X": [1, 0, 0], "Y": [0, 1, 0], "A": [1, -1, 0], "B": [1, 1, 0]}.items():
            with self.subTest(axis=axis):
                printer = FakePrinter()
                _, plugin = load_plugin(printer)
                plugin.cmd_excite(FakeGCmd(AXIS=axis, FREQUENCY=40, DURATION=1, RECORD=0, OUTPUT_DIR=tempfile.gettempdir()))
                self.assertEqual(printer.resonance_tester.moves[0][1]["direction_vector"], vector)

    def test_static_frequency_unsafe_refusal_before_motion(self) -> None:
        printer = FakePrinter()
        printer.printing = True
        module, plugin = load_plugin(printer)
        with self.assertRaisesRegex(module.CommandError, "printing"):
            plugin.cmd_excite(FakeGCmd(AXIS="X", FREQUENCY=40, DURATION=1, OUTPUT_DIR=tempfile.gettempdir()))
        self.assertEqual(printer.resonance_tester.moves, [])

    def test_static_frequency_success_with_and_without_recording(self) -> None:
        printer = FakePrinter()
        _, plugin = load_plugin(printer)
        with tempfile.TemporaryDirectory() as temp_dir:
            no_record = FakeGCmd(AXIS="X", FREQUENCY=40, DURATION=1, RECORD=0, OUTPUT_DIR=temp_dir)
            plugin.cmd_excite(no_record)
            self.assertIn("excitation complete", no_record.responses[0])
            self.assertNotIn("path=", no_record.responses[0])
            self.assertEqual(list(Path(temp_dir).glob("*.sbcapture.json")), [])

            record = FakeGCmd(AXIS="A", FREQUENCY=45, DURATION=1, RECORD=1, OUTPUT_DIR=temp_dir)
            plugin.cmd_excite(record)
            captures = list(Path(temp_dir).glob("*.sbcapture.json"))
            self.assertEqual(len(captures), 1)
            data = json.loads(captures[0].read_text())
        self.assertEqual(data["tool"], "static-frequency")
        self.assertEqual(data["command"], "SHAKEANDBAKE_EXCITE")
        self.assertEqual(data["measurements"][0]["metadata"]["axis_label"], "A")
        self.assertEqual(data["measurements"][0]["metadata"]["direction_vector"], [1, -1, 0])
        self.assertEqual(data["measurements"][0]["metadata"]["frequency"], 45.0)
        self.assertTrue(printer.input_shaper.state["enabled"])
        self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)

    def test_static_frequency_forced_failures_restore_state(self) -> None:
        for failure in ["motion", "sampling", "writing"]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                printer = FakePrinter()
                module, plugin = load_plugin(printer)
                if failure == "motion":
                    printer.resonance_tester.fail = True
                if failure == "sampling":
                    printer.lis2dw.fail = True
                patcher = mock.patch.object(module, "write_capture_artifact", side_effect=RuntimeError("write failure"))
                context = patcher if failure == "writing" else _null_context()
                with context:
                    with self.assertRaises(Exception):
                        plugin.cmd_excite(FakeGCmd(AXIS="X", FREQUENCY=40, DURATION=1, RECORD=1, OUTPUT_DIR=temp_dir))
                self.assertTrue(printer.input_shaper.state["enabled"])
                self.assertEqual(printer.toolhead.velocity_limits["max_velocity"], 600.0)
                self.assertGreaterEqual(printer.input_shaper.restores, 1)
                self.assertGreaterEqual(printer.toolhead.restores, 1)

    def test_restoration_failures_are_reported_distinctly(self) -> None:
        printer = FakePrinter()
        printer.input_shaper.fail_restore = True
        _, plugin = load_plugin(printer)
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = FakeGCmd(AXIS="X", OUTPUT_DIR=temp_dir)
            plugin.cmd_capture_shaper(cmd)
            captures = list(Path(temp_dir).glob("*.sbcapture.json"))
            data = json.loads(captures[0].read_text())

        self.assertTrue(any("restoration warnings" in response for response in cmd.responses))
        self.assertFalse(data["metadata"]["restoration_status"]["ok"])
        self.assertIn("input_shaper_restore_failed", data["metadata"]["restoration_status"]["errors"][0])


class _null_context:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


if __name__ == "__main__":
    unittest.main()
