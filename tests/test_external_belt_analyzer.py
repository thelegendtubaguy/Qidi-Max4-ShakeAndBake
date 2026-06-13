from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shakeandbake_analyze import BeltAnalysisOptions, analyze_belt_capture
from shakeandbake_analyze import belts

BELT_FIXTURES = Path(__file__).parent / "fixtures" / "belts"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class ExternalBeltAnalyzerTests(unittest.TestCase):
    def test_cli_analyzes_valid_belt_capture_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "shakeandbake_analyze",
                    "analyze",
                    "belts",
                    str(BELT_FIXTURES / "valid_ab.json"),
                    "--output-dir",
                    temp_dir,
                ],
                cwd=Path(__file__).parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = Path(temp_dir)
            analysis = json.loads((output / "analysis-belts.json").read_text())
            self.assertTrue(analysis["comparison_valid"])
            self.assertEqual(set(analysis["paths"]), {"A", "B"})
            self.assertIn("normalized_area_difference", analysis["comparison"]["metrics"])
            self.assertEqual(analysis["comparison"]["metrics"]["correlation"]["status"], "valid")
            self.assertTrue(analysis["comparison"]["paired_peaks"])
            self.assertTrue((output / "summary.txt").exists())
            self.assertTrue((output / "graphs" / "belt-psd-overlay.svg").exists())
            self.assertTrue((output / "graphs" / "belt-peak-pairs.svg").exists())
            self.assertIn("source_fingerprint", analysis)

    def test_json_only_disables_summary_and_graphs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_belt_capture(
                BELT_FIXTURES / "valid_ab.json",
                temp_dir,
                BeltAnalysisOptions(json_only=True, graphs_enabled=False),
            )
            output = Path(temp_dir)

            self.assertTrue(result.comparison_valid)
            self.assertTrue((output / "analysis-belts.json").exists())
            self.assertFalse((output / "summary.txt").exists())
            self.assertFalse((output / "graphs").exists())

    def test_import_does_not_import_or_initialize_klipper_modules(self) -> None:
        script = """
import sys
import shakeandbake_analyze.belts
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

    def test_missing_paths_block_comparison(self) -> None:
        for fixture, missing in [("missing_a.json", "A"), ("missing_b.json", "B")]:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as temp_dir:
                result = analyze_belt_capture(BELT_FIXTURES / fixture, temp_dir)
                analysis = json.loads((Path(temp_dir) / "analysis-belts.json").read_text())

                self.assertTrue(result.blocked)
                self.assertFalse(result.comparison_valid)
                self.assertIn("missing_path", [item["code"] for item in analysis["diagnostics"]])
                self.assertIn(missing, [item["path"] for item in analysis["diagnostics"] if item["code"] == "missing_path"])

    def test_invalid_sample_fixtures_block_at_validation_gate(self) -> None:
        for fixture in ["invalid_nonmonotonic.json", "invalid_nonfinite.json", "invalid_constant.json"]:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as temp_dir:
                result = analyze_belt_capture(BELT_FIXTURES / fixture, temp_dir)
                analysis = json.loads((Path(temp_dir) / "analysis-belts.json").read_text())

                self.assertTrue(result.blocked)
                self.assertFalse(result.comparison_valid)
                self.assertTrue(analysis["diagnostics"])

    def test_degenerate_psd_blocks_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(belts, "_welch_psd", return_value=([10.0, 20.0, 30.0], [1.0, 1.0, 1.0], {"method": "test"})):
                result = analyze_belt_capture(BELT_FIXTURES / "valid_ab.json", temp_dir)
            analysis = json.loads((Path(temp_dir) / "analysis-belts.json").read_text())

        self.assertTrue(result.blocked)
        self.assertIn("invalid_psd", [item["code"] for item in analysis["diagnostics"]])

    def test_paired_and_unpaired_peak_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyze_belt_capture(
                BELT_FIXTURES / "paired_unpaired_peaks.json",
                temp_dir,
                BeltAnalysisOptions(peak_pairing_threshold_hz=5.0),
            )
            analysis = json.loads((Path(temp_dir) / "analysis-belts.json").read_text())

        self.assertTrue(analysis["comparison"]["paired_peaks"])
        self.assertTrue(analysis["comparison"]["unpaired_a_peaks"] or analysis["comparison"]["unpaired_b_peaks"])
        self.assertIn("unpaired_peaks", [item["code"] for item in analysis["warnings"]])
        pair = analysis["comparison"]["paired_peaks"][0]
        self.assertIn("frequency_delta_hz", pair)
        self.assertIn("amplitude_ratio_b_over_a", pair)

    def test_correlation_unavailable_for_constant_arrays_has_no_nan(self) -> None:
        diagnostics = []
        metrics = belts._comparison_metrics([1.0, 1.0, 1.0], [2.0, 2.0, 2.0], diagnostics)

        self.assertEqual(metrics["correlation"]["status"], "unavailable")
        self.assertIn("correlation_unavailable", [item["code"] for item in diagnostics])
        self.assertNotIn("NaN", json.dumps(metrics))

    def test_motor_metadata_reporting_and_raw_capture_immutability(self) -> None:
        capture = BELT_FIXTURES / "valid_ab.json"
        before = sha256(capture)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_belt_capture(capture, temp_dir)
            analysis = json.loads((Path(temp_dir) / "analysis-belts.json").read_text())
            summary = (Path(temp_dir) / "summary.txt").read_text()

        self.assertTrue(result.comparison_valid)
        self.assertEqual(sha256(capture), before)
        self.assertIn("x", analysis["motor_metadata"])
        self.assertEqual(analysis["motor_metadata"]["x"]["run_current"], 1.2)
        self.assertIn("Motor metadata", summary)


if __name__ == "__main__":
    unittest.main()
