from __future__ import annotations

import json
import unittest
from pathlib import Path

from shakeandbake_capture import Sample
from shakeandbake_max4 import (
    AdapterSnapshot,
    OrientationValidationRequest,
    STATUS_AMBIGUOUS,
    STATUS_INSUFFICIENT_SIGNAL,
    STATUS_MISMATCH,
    STATUS_NOISY,
    STATUS_UNAVAILABLE,
    STATUS_VALID,
    TestPreflightAdapter,
    analyze_orientation_samples,
    parse_max4_config,
    plan_orientation_moves,
    validate_lis2dw_orientation,
)

FIXTURES = Path(__file__).parent / "fixtures"


def rows_to_samples(rows):
    return [Sample.from_value(row) for row in rows]


def load_orientation_fixture(name: str):
    data = json.loads((FIXTURES / "orientation" / name).read_text())
    return data, {axis: rows_to_samples(rows) for axis, rows in data.get("samples", {}).items()}


class FakeOrientationAdapter(TestPreflightAdapter):
    def __init__(self, samples_by_axis, state=None, fail_axis=None) -> None:
        super().__init__(state or AdapterSnapshot(host_load=0.1, free_memory_mb=2048, free_disk_mb=4096))
        self.samples_by_axis = samples_by_axis
        self.fail_axis = fail_axis
        self.input_state = {"enabled": True}
        self.velocity_state = {"max_velocity": 600.0}
        self.restored_input = False
        self.restored_velocity = False
        self.plans = []

    def acquire_orientation_samples(self, plan):
        self.plans.append(plan)
        if plan.axis == self.fail_axis:
            raise RuntimeError("forced validation acquisition failure")
        return self.samples_by_axis[plan.axis]

    def snapshot_input_shaper(self):
        return dict(self.input_state)

    def disable_input_shaper(self):
        self.input_state["enabled"] = False

    def restore_input_shaper(self, snapshot):
        self.input_state = dict(snapshot)
        self.restored_input = True

    def snapshot_velocity_limits(self):
        return dict(self.velocity_state)

    def update_velocity_limits(self, params=None):
        self.velocity_state["max_velocity"] = 100.0

    def restore_velocity_limits(self, snapshot):
        self.velocity_state = dict(snapshot)
        self.restored_velocity = True


class Lis2dwOrientationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = parse_max4_config(FIXTURES / "max4" / "stock_printer.cfg")

    def test_x_and_y_dominant_channel_and_polarity_for_stock_axes_map(self) -> None:
        data, samples = load_orientation_fixture("stock_axes_map.json")

        x = analyze_orientation_samples("x", samples["x"], data["axes_map"])
        y = analyze_orientation_samples("y", samples["y"], data["axes_map"])

        self.assertEqual(x.status, STATUS_VALID)
        self.assertEqual(x.dominant_channel, "accel_y")
        self.assertEqual(x.polarity_hint, "positive")
        self.assertGreater(x.dominance_ratio, 10)
        self.assertIsNotNone(x.sample_rate_hz)
        self.assertEqual(y.status, STATUS_VALID)
        self.assertEqual(y.dominant_channel, "accel_z")
        self.assertEqual(y.polarity_hint, "positive")

    def test_inverted_axes_map_polarity_hint(self) -> None:
        data, samples = load_orientation_fixture("inverted_axes_map.json")

        x = analyze_orientation_samples("x", samples["x"], data["axes_map"])
        y = analyze_orientation_samples("y", samples["y"], data["axes_map"])

        self.assertEqual(x.status, STATUS_VALID)
        self.assertEqual(x.dominant_channel, "accel_y")
        self.assertEqual(x.polarity_hint, "negative")
        self.assertEqual(y.status, STATUS_VALID)
        self.assertEqual(y.dominant_channel, "accel_z")
        self.assertEqual(y.polarity_hint, "negative")

    def test_ambiguous_missing_and_noisy_statuses(self) -> None:
        ambiguous_data, ambiguous_samples = load_orientation_fixture("ambiguous_xy_response.json")
        missing_data, missing_samples = load_orientation_fixture("missing_signal.json")
        noisy_data, noisy_samples = load_orientation_fixture("noisy_signal.json")

        ambiguous = analyze_orientation_samples("x", ambiguous_samples["x"], ambiguous_data["axes_map"])
        missing = analyze_orientation_samples("x", missing_samples["x"], missing_data["axes_map"])
        noisy = analyze_orientation_samples("x", noisy_samples["x"], noisy_data["axes_map"])

        self.assertEqual(ambiguous.status, STATUS_AMBIGUOUS)
        self.assertEqual(missing.status, STATUS_INSUFFICIENT_SIGNAL)
        self.assertEqual(noisy.status, STATUS_NOISY)

    def test_mismatch_diagnostic_without_config_mutation(self) -> None:
        data, samples = load_orientation_fixture("stock_axes_map.json")
        original_axes_map = data["axes_map"]

        result = analyze_orientation_samples("x", samples["x"], "x,y,z")

        self.assertEqual(result.status, STATUS_MISMATCH)
        self.assertEqual(result.diagnostics[0].code, "axes_map_mismatch")
        self.assertEqual(data["axes_map"], original_axes_map)

    def test_z_axis_validation_request_is_rejected_before_motion(self) -> None:
        _, samples = load_orientation_fixture("stock_axes_map.json")
        adapter = FakeOrientationAdapter(samples)

        summary = validate_lis2dw_orientation(OrientationValidationRequest(axes=("z",)), self.config, adapter)

        self.assertEqual(summary.status, STATUS_UNAVAILABLE)
        self.assertEqual(summary.diagnostics[0].code, "z_axis_unsupported")
        self.assertEqual(adapter.plans, [])

    def test_plan_short_bounded_xy_moves(self) -> None:
        plans = plan_orientation_moves(self.config, OrientationValidationRequest())

        self.assertEqual([plan.axis for plan in plans], ["x", "y"])
        self.assertEqual(plans[0].start, (195.0, 195.0, 10.0))
        self.assertEqual(plans[0].end, (200.0, 195.0, 10.0))
        self.assertEqual(plans[1].end, (195.0, 200.0, 10.0))

    def test_preflight_blocks_orientation_validation_before_motion(self) -> None:
        _, samples = load_orientation_fixture("stock_axes_map.json")
        adapter = FakeOrientationAdapter(samples, AdapterSnapshot(printer_ready=False))

        summary = validate_lis2dw_orientation(OrientationValidationRequest(), self.config, adapter)

        self.assertEqual(summary.status, STATUS_UNAVAILABLE)
        self.assertEqual(summary.diagnostics[0].code, "printer_not_ready")
        self.assertEqual(adapter.plans, [])

    def test_validation_acquires_xy_samples_and_restores_state_on_failure(self) -> None:
        _, samples = load_orientation_fixture("stock_axes_map.json")
        adapter = FakeOrientationAdapter(samples, fail_axis="y")

        summary = validate_lis2dw_orientation(OrientationValidationRequest(), self.config, adapter)

        self.assertEqual(summary.results["x"].status, STATUS_VALID)
        self.assertEqual(summary.results["y"].status, STATUS_UNAVAILABLE)
        self.assertEqual(summary.results["y"].diagnostics[0].code, "sample_acquisition_failed")
        self.assertTrue(adapter.input_state["enabled"])
        self.assertEqual(adapter.velocity_state["max_velocity"], 600.0)
        self.assertTrue(adapter.restored_input)
        self.assertTrue(adapter.restored_velocity)

    def test_preflight_and_capture_metadata_include_orientation_summary(self) -> None:
        from tests.test_klipper_data_acquisition import FakeGCmd, FakePrinter, load_plugin

        data, samples = load_orientation_fixture("stock_axes_map.json")
        summary = validate_lis2dw_orientation(OrientationValidationRequest(), self.config, FakeOrientationAdapter(samples))
        printer = FakePrinter()
        printer.orientation_validation_summary = summary.to_dict()
        _, plugin = load_plugin(printer)

        preflight_cmd = FakeGCmd()
        plugin.cmd_preflight(preflight_cmd)
        self.assertIn("orientation_status=valid", preflight_cmd.responses[0])
        self.assertIn("orientation_axes_map=y,z,-x", preflight_cmd.responses[0])

        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_cmd = FakeGCmd(AXIS="X", OUTPUT_DIR=temp_dir)
            plugin.cmd_capture_shaper(capture_cmd)
            capture = next(Path(temp_dir).glob("*.sbcapture.json"))
            capture_data = json.loads(capture.read_text())
        self.assertEqual(capture_data["metadata"]["orientation_validation_summary"]["status"], "valid")
        self.assertEqual(capture_data["metadata"]["orientation_validation_summary"]["configured_axes_map"], "y,z,-x")
        self.assertNotIn("z", capture_data["metadata"]["orientation_validation_summary"]["results"])


if __name__ == "__main__":
    unittest.main()
