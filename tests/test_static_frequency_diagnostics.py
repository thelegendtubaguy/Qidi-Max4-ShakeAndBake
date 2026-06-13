from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shakeandbake_analyze import StaticFrequencyAnalysisOptions, analyze_static_frequency_capture

FIXTURES = Path(__file__).parent / "fixtures" / "static_frequency"


class StaticFrequencyDiagnosticsTests(unittest.TestCase):
    def test_cli_analyzes_valid_static_frequency_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "shakeandbake_analyze",
                    "analyze",
                    "static-frequency",
                    str(FIXTURES / "valid_static_x.json"),
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
            analysis = json.loads((output / "analysis-static-frequency.json").read_text())
            self.assertTrue(analysis["analysis_valid"])
            self.assertEqual(analysis["static_frequency"]["axis_label"], "X")
            self.assertTrue(analysis["static_frequency"]["spectrogram"]["frames"])
            self.assertTrue(analysis["static_frequency"]["cumulative_energy"])
            self.assertTrue((output / "summary.txt").exists())
            self.assertTrue((output / "graphs" / "static-frequency-spectrogram.svg").exists())
            self.assertTrue((output / "graphs" / "static-frequency-energy.svg").exists())

    def test_json_only_disables_summary_and_graphs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_static_frequency_capture(
                FIXTURES / "valid_static_x.json",
                temp_dir,
                StaticFrequencyAnalysisOptions(json_only=True, graphs_enabled=False),
            )
            output = Path(temp_dir)
            self.assertTrue(result.analysis_valid)
            self.assertTrue((output / "analysis-static-frequency.json").exists())
            self.assertFalse((output / "summary.txt").exists())
            self.assertFalse((output / "graphs").exists())

    def test_invalid_capture_and_unsupported_axis_are_diagnostic(self) -> None:
        for fixture, code in [("invalid_time.json", "nonmonotonic_time"), ("unsupported_axis_z.json", "unsupported_axis")]:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as temp_dir:
                result = analyze_static_frequency_capture(FIXTURES / fixture, temp_dir)
                analysis = json.loads((Path(temp_dir) / "analysis-static-frequency.json").read_text())
                self.assertTrue(result.blocked)
                self.assertFalse(result.analysis_valid)
                self.assertIn(code, [item["code"] for item in analysis["diagnostics"]])


if __name__ == "__main__":
    unittest.main()
