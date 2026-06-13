from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shakeandbake_capture import (
    REQUIRED_SAMPLE_COLUMNS,
    STATUS_CONSTANT_SIGNAL,
    STATUS_DERIVED_OUTPUT_IN_RAW_CAPTURE,
    STATUS_INSUFFICIENT_SAMPLES,
    STATUS_INVALID_Z_AXIS_CALIBRATION,
    STATUS_MISSING_REQUIRED_FIELD,
    STATUS_NONFINITE_SAMPLE,
    STATUS_NONMONOTONIC_TIME,
    STATUS_UNSUPPORTED_SCHEMA,
    read_capture_artifact,
    validate_capture_artifact,
    write_capture_artifact,
)

FIXTURES = Path(__file__).parent / "fixtures" / "capture_artifacts"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class CaptureArtifactTests(unittest.TestCase):
    def test_valid_max4_xy_lis2dw_fixture_reads_and_validates(self) -> None:
        result = read_capture_artifact(FIXTURES / "valid_max4_xy_lis2dw.json")

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.artifact)
        assert result.artifact is not None
        self.assertEqual(result.artifact.printer_model, "qidi_max_4")
        self.assertEqual(result.artifact.measurements[0].sensor, "lis2dw")
        self.assertEqual(tuple(result.artifact.measurements[0].columns), REQUIRED_SAMPLE_COLUMNS)
        self.assertEqual(result.artifact.measurements[0].samples[0].time, 0.0)
        self.assertEqual(result.artifact.measurements[0].samples[0].accel_x, 0.10)

    def test_invalid_fixtures_return_structured_diagnostics(self) -> None:
        cases = [
            ("invalid_empty_data.json", STATUS_INSUFFICIENT_SAMPLES),
            ("invalid_one_sample.json", STATUS_INSUFFICIENT_SAMPLES),
            ("invalid_nonmonotonic_time.json", STATUS_NONMONOTONIC_TIME),
            ("invalid_nonfinite_samples.json", STATUS_NONFINITE_SAMPLE),
            ("invalid_constant_signal.json", STATUS_CONSTANT_SIGNAL),
            ("invalid_missing_metadata.json", STATUS_MISSING_REQUIRED_FIELD),
            ("invalid_unsupported_schema.json", STATUS_UNSUPPORTED_SCHEMA),
        ]
        for fixture, status in cases:
            with self.subTest(fixture=fixture):
                result = read_capture_artifact(FIXTURES / fixture)

                self.assertEqual(result.validation.status, status)
                self.assertTrue(result.validation.diagnostics)
                diagnostic = result.validation.diagnostics[0]
                self.assertEqual(diagnostic.status_code, status)
                self.assertTrue(diagnostic.message)
                self.assertTrue(diagnostic.field_path)

    def test_writer_emits_capture_and_optional_metadata_sidecar(self) -> None:
        artifact = load_fixture("valid_max4_xy_lis2dw.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "capture.sbcapture.json"

            result = write_capture_artifact(output, artifact, emit_metadata_sidecar=True)

            self.assertTrue(result.ok)
            self.assertTrue(output.exists())
            self.assertIsNotNone(result.metadata_sidecar_path)
            assert result.metadata_sidecar_path is not None
            sidecar = Path(result.metadata_sidecar_path)
            self.assertTrue(sidecar.exists())
            sidecar_data = json.loads(sidecar.read_text())
            self.assertEqual(sidecar_data["metadata"]["axes_map"]["toolhead_x"], "sensor_x")
            self.assertNotIn("samples", sidecar_data["measurements"][0])

    def test_writer_preserves_unknown_fields_on_round_trip(self) -> None:
        artifact = load_fixture("valid_max4_xy_lis2dw.json")
        artifact["metadata"]["operator_note"] = "keep me"
        artifact["unknown_root"] = {"vendor": "qidi"}
        artifact["measurements"][0]["unknown_measurement"] = "also keep me"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "roundtrip.sbcapture.json"

            result = write_capture_artifact(output, artifact)
            self.assertTrue(result.ok)
            roundtrip = json.loads(output.read_text())

        self.assertEqual(roundtrip["metadata"]["operator_note"], "keep me")
        self.assertEqual(roundtrip["unknown_root"], {"vendor": "qidi"})
        self.assertEqual(roundtrip["measurements"][0]["unknown_measurement"], "also keep me")

    def test_writer_is_atomic_when_final_rename_fails(self) -> None:
        from shakeandbake_capture import artifacts

        artifact = load_fixture("valid_max4_xy_lis2dw.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output = temp_path / "capture.sbcapture.json"
            output.write_text("original\n")

            def fail_replace(src: Path, dst: Path) -> None:
                raise OSError("simulated rename failure")

            with mock.patch.object(artifacts.os, "replace", fail_replace):
                with self.assertRaisesRegex(OSError, "simulated rename failure"):
                    write_capture_artifact(output, artifact)

            self.assertEqual(output.read_text(), "original\n")
            self.assertEqual(list(temp_path.glob(".capture.sbcapture.json.tmp-*")), [])

    def test_capture_package_imports_without_heavy_or_klipper_dependencies(self) -> None:
        script = """
import sys
import shakeandbake_capture
forbidden = ('numpy', 'scipy', 'matplotlib', 'zstandard', 'klipper')
loaded = sorted(name for name in sys.modules if name == 'klipper' or name.startswith(forbidden))
print(loaded)
raise SystemExit(1 if loaded else 0)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            text=True,
            capture_output=True,
            cwd=Path(__file__).parents[1],
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_raw_capture_rejects_analysis_outputs(self) -> None:
        artifact = load_fixture("valid_max4_xy_lis2dw.json")
        artifact["metadata"]["graph_path"] = "graphs/x.png"

        result = validate_capture_artifact(artifact)

        self.assertEqual(result.status, STATUS_DERIVED_OUTPUT_IN_RAW_CAPTURE)
        self.assertEqual(result.diagnostics[0].field_path, "$.metadata.graph_path")

    def test_max4_z_axis_calibration_semantics_are_rejected(self) -> None:
        artifact = load_fixture("valid_max4_xy_lis2dw.json")
        artifact["measurements"][0]["axis"] = "z"

        result = validate_capture_artifact(artifact)

        self.assertEqual(result.status, STATUS_INVALID_Z_AXIS_CALIBRATION)
        self.assertEqual(result.diagnostics[0].measurement_name, "x_sweep")


if __name__ == "__main__":
    unittest.main()
