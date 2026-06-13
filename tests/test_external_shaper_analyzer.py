from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shakeandbake_analyze import ShaperAnalysisOptions, analyze_shaper_capture
from shakeandbake_analyze.shaper import _estimate_damping

SHAPER_FIXTURES = Path(__file__).parent / "fixtures" / "shaper"
CAPTURE_FIXTURES = Path(__file__).parent / "fixtures" / "capture_artifacts"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class ExternalShaperAnalyzerTests(unittest.TestCase):
    def test_cli_analyzes_valid_xy_capture_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "shakeandbake_analyze",
                    "analyze",
                    "shaper",
                    str(SHAPER_FIXTURES / "valid_xy.json"),
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
            analysis = json.loads((output / "analysis-shaper.json").read_text())
            self.assertTrue(analysis["recommendations_available"])
            self.assertEqual(set(analysis["recommendations"]), {"x", "y"})
            self.assertTrue((output / "summary.txt").exists())
            self.assertTrue((output / "input-shaper.proposed.cfg").exists())
            self.assertTrue((output / "graphs" / "x-psd.svg").exists())
            self.assertTrue((output / "graphs" / "y-psd.svg").exists())
            self.assertIn("source_fingerprint", analysis)
            self.assertIn("frequency_resolution_hz", analysis["axes"]["x"])
            self.assertIn("peaks", analysis["axes"]["x"])
            self.assertIn("candidates", analysis["axes"]["x"])

    def test_json_only_disables_summary_graphs_and_cfg_still_when_recommended(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_shaper_capture(
                SHAPER_FIXTURES / "valid_x_only.json",
                temp_dir,
                ShaperAnalysisOptions(json_only=True, graphs_enabled=False),
            )
            output = Path(temp_dir)

            self.assertTrue(result.recommendations_available)
            self.assertTrue((output / "analysis-shaper.json").exists())
            self.assertFalse((output / "summary.txt").exists())
            self.assertFalse((output / "graphs").exists())
            self.assertTrue((output / "input-shaper.proposed.cfg").exists())

    def test_import_does_not_import_or_initialize_klipper_modules(self) -> None:
        script = """
import sys
import shakeandbake_analyze
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

    def test_invalid_capture_blocks_recommendations_and_writes_diagnostics(self) -> None:
        fixtures = [
            "invalid_empty_data.json",
            "invalid_one_sample.json",
            "invalid_nonmonotonic_time.json",
            "invalid_nonfinite_samples.json",
            "invalid_constant_signal.json",
            "invalid_missing_metadata.json",
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as temp_dir:
                result = analyze_shaper_capture(CAPTURE_FIXTURES / fixture, temp_dir)
                analysis = json.loads((Path(temp_dir) / "analysis-shaper.json").read_text())

                self.assertTrue(result.blocked)
                self.assertFalse(result.recommendations_available)
                self.assertTrue(analysis["diagnostics"])
                self.assertFalse((Path(temp_dir) / "input-shaper.proposed.cfg").exists())

    def test_missing_axis_and_z_only_captures_block_or_ignore_with_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_shaper_capture(SHAPER_FIXTURES / "missing_axis_blocks.json", temp_dir)
            analysis = json.loads((Path(temp_dir) / "analysis-shaper.json").read_text())
            self.assertTrue(result.blocked)
            self.assertIn("missing_axis_blocks", [item["code"] for item in analysis["diagnostics"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_shaper_capture(SHAPER_FIXTURES / "z_only.json", temp_dir)
            analysis = json.loads((Path(temp_dir) / "analysis-shaper.json").read_text())
            self.assertTrue(result.blocked)
            codes = [item["code"] for item in analysis["diagnostics"]]
            self.assertIn("z_axis_ignored", codes)
            self.assertIn("missing_axis_blocks", codes)

    def test_synthetic_resonance_peak_and_recommendation_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyze_shaper_capture(SHAPER_FIXTURES / "synthetic_resonance_xy.json", temp_dir)
            analysis = json.loads((Path(temp_dir) / "analysis-shaper.json").read_text())

        x_peak = analysis["axes"]["x"]["peaks"][0]["frequency_hz"]
        y_peak = analysis["axes"]["y"]["peaks"][0]["frequency_hz"]
        self.assertAlmostEqual(x_peak, 39.0625, places=3)
        self.assertAlmostEqual(y_peak, 54.6875, places=3)
        self.assertIn(analysis["recommendations"]["x"]["selected_shaper"], {"mzv", "ei", "2hump_ei", "3hump_ei"})
        self.assertIn(analysis["recommendations"]["y"]["selected_shaper"], {"mzv", "ei", "2hump_ei", "3hump_ei"})

    def test_damping_uses_psd_half_power_peak_over_two_crossings(self) -> None:
        frequencies = [10, 20, 30, 40, 50, 60, 70]
        psd = [1, 2, 5, 10, 5, 2, 1]

        damping = _estimate_damping(frequencies, psd, 40)

        self.assertEqual(damping["status"], "valid")
        self.assertEqual(damping["half_power"], 5)
        self.assertEqual(damping["lower_hz"], 30)
        self.assertEqual(damping["upper_hz"], 50)
        self.assertAlmostEqual(damping["ratio"], 0.25)

    def test_outputs_do_not_modify_raw_capture_or_printer_config(self) -> None:
        capture = SHAPER_FIXTURES / "valid_xy.json"
        before = sha256(capture)
        with tempfile.TemporaryDirectory() as temp_dir:
            printer_cfg = Path(temp_dir) / "printer.cfg"
            printer_cfg.write_text("[input_shaper]\nshaper_type_x: mzv\n")
            printer_before = sha256(printer_cfg)

            analyze_shaper_capture(capture, temp_dir)

            self.assertEqual(sha256(capture), before)
            self.assertEqual(sha256(printer_cfg), printer_before)
            self.assertTrue((Path(temp_dir) / "input-shaper.proposed.cfg").exists())
            self.assertTrue((Path(temp_dir) / "analysis-shaper.json").exists())


if __name__ == "__main__":
    unittest.main()
