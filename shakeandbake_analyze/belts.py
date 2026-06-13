from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import MeasurementBlock, read_capture_artifact

from .shaper import _center_samples, _detect_peaks, _json_safe, _validate_psd, _welch_psd


@dataclass(frozen=True)
class BeltAnalysisOptions:
    graphs_enabled: bool = True
    json_only: bool = False
    peak_pairing_threshold_hz: float = 5.0
    peak_relative_threshold: float = 0.25
    peak_absolute_threshold: float = 1e-12
    max_peak_count_warning: int = 8
    min_frequency_hz: float = 5.0
    max_frequency_hz: float = 140.0


@dataclass(frozen=True)
class BeltAnalysisResult:
    output_dir: str
    analysis_path: str
    summary_path: Optional[str]
    graph_paths: Tuple[str, ...]
    blocked: bool
    comparison_valid: bool


def analyze_belt_capture(
    capture_file: str | Path,
    output_dir: str | Path,
    options: BeltAnalysisOptions | None = None,
) -> BeltAnalysisResult:
    options = options or BeltAnalysisOptions()
    capture_path = Path(capture_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    diagnostics: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    analysis: Dict[str, Any] = {
        "source_capture": str(capture_path),
        "source_fingerprint": _sha256(capture_path) if capture_path.exists() else None,
        "validation": {"valid": False, "status": "not_run", "diagnostics": []},
        "paths": {},
        "comparison": {},
        "warnings": warnings,
        "diagnostics": diagnostics,
        "motor_metadata": {},
    }

    read_result = read_capture_artifact(capture_path)
    analysis["validation"] = _validation_to_dict(read_result.validation)
    if read_result.artifact is None or not read_result.validation.valid:
        diagnostics.extend(analysis["validation"]["diagnostics"])
        return _write_outputs(output_path, analysis, options, blocked=True)

    artifact = read_result.artifact
    analysis["motor_metadata"] = _motor_metadata(artifact.metadata)
    blocks = _select_belt_blocks(artifact.measurements)
    missing = [path for path in ("A", "B") if path not in blocks]
    for path in missing:
        diagnostics.append(_diagnostic("missing_path", f"missing belt path {path} measurement", path=path))
    if missing:
        return _write_outputs(output_path, analysis, options, blocked=True)

    psds: Dict[str, Tuple[List[float], List[float]]] = {}
    for path_label in ("A", "B"):
        path_result = _analyze_path(path_label, blocks[path_label], options, warnings, diagnostics)
        analysis["paths"][path_label] = path_result
        if path_result.get("valid"):
            psd = path_result["psd"]
            psds[path_label] = (psd["frequencies_hz"], psd["values"])

    if set(psds) != {"A", "B"}:
        diagnostics.append(_diagnostic("invalid_psd", "A and B PSDs are required for comparison"))
        return _write_outputs(output_path, analysis, options, blocked=True)

    common_frequencies, a_values, b_values = _common_grid(psds["A"], psds["B"])
    a_peaks = _detect_peaks(common_frequencies, a_values, options)  # type: ignore[arg-type]
    b_peaks = _detect_peaks(common_frequencies, b_values, options)  # type: ignore[arg-type]
    pairs, unpaired_a, unpaired_b = _pair_peaks(a_peaks, b_peaks, options.peak_pairing_threshold_hz)
    metrics = _comparison_metrics(a_values, b_values, diagnostics)
    if len(a_peaks) > options.max_peak_count_warning or len(b_peaks) > options.max_peak_count_warning:
        warnings.append(_warning("excessive_peak_count", "peak count exceeds configured warning threshold"))
    if unpaired_a or unpaired_b:
        warnings.append(_warning("unpaired_peaks", "one or more A/B peaks could not be paired"))
    _aliasing_warnings(blocks, analysis["paths"], warnings)

    analysis["comparison"] = {
        "status": "comparison_valid",
        "common_frequency_grid_hz": common_frequencies,
        "peaks": {"A": a_peaks, "B": b_peaks},
        "paired_peaks": pairs,
        "unpaired_a_peaks": unpaired_a,
        "unpaired_b_peaks": unpaired_b,
        "metrics": metrics,
    }
    return _write_outputs(output_path, analysis, options, blocked=False)


def _select_belt_blocks(measurements: Sequence[MeasurementBlock]) -> Dict[str, MeasurementBlock]:
    selected: Dict[str, MeasurementBlock] = {}
    for measurement in measurements:
        label = str(measurement.metadata.get("path_label", "")).upper()
        if label in ("A", "B") and label not in selected:
            selected[label] = measurement
    return selected


def _analyze_path(
    path_label: str,
    measurement: MeasurementBlock,
    options: BeltAnalysisOptions,
    warnings: List[Dict[str, Any]],
    diagnostics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sample_rate = _derive_sample_rate(measurement.samples)
    result: Dict[str, Any] = {
        "valid": False,
        "measurement": measurement.name,
        "path_label": path_label,
        "direction_vector": measurement.metadata.get("direction_vector"),
        "sample_rate_hz": sample_rate,
        "diagnostics": [],
        "warnings": [],
        "psd_metadata": {},
        "peaks": [],
    }
    if sample_rate is None or sample_rate <= 0:
        diagnostic = _diagnostic("invalid_sample_rate", "sample rate is not usable", path=path_label)
        diagnostics.append(diagnostic)
        result["diagnostics"].append(diagnostic)
        return result
    centered = _center_samples(measurement.samples)
    shaper_options = _ShaperLikeOptions(options)
    frequencies, values, metadata = _welch_psd(centered, sample_rate, shaper_options)  # type: ignore[arg-type]
    result["psd_metadata"] = metadata
    issue = _validate_psd(frequencies, values)
    if issue:
        diagnostic = _diagnostic("invalid_psd", issue, path=path_label)
        diagnostics.append(diagnostic)
        result["diagnostics"].append(diagnostic)
        return result
    peaks = _detect_peaks(frequencies, values, shaper_options)  # type: ignore[arg-type]
    result.update(
        {
            "valid": True,
            "psd": {"frequencies_hz": frequencies, "values": values},
            "peaks": peaks,
        }
    )
    if not peaks:
        warning = _warning("insufficient_signal", "no belt-path peaks exceeded detection thresholds", path=path_label)
        warnings.append(warning)
        result["warnings"].append(warning)
    return result


class _ShaperLikeOptions:
    def __init__(self, options: BeltAnalysisOptions):
        self.min_frequency_hz = options.min_frequency_hz
        self.max_frequency_hz = options.max_frequency_hz
        self.peak_relative_threshold = options.peak_relative_threshold
        self.peak_absolute_threshold = options.peak_absolute_threshold


def _common_grid(
    a: Tuple[Sequence[float], Sequence[float]], b: Tuple[Sequence[float], Sequence[float]]
) -> Tuple[List[float], List[float], List[float]]:
    a_freq, a_values = a
    b_freq, b_values = b
    start = max(min(a_freq), min(b_freq))
    end = min(max(a_freq), max(b_freq))
    base = a_freq if len(a_freq) <= len(b_freq) else b_freq
    grid = [frequency for frequency in base if start <= frequency <= end]
    return grid, [_interp(f, a_freq, a_values) for f in grid], [_interp(f, b_freq, b_values) for f in grid]


def _interp(frequency: float, frequencies: Sequence[float], values: Sequence[float]) -> float:
    if frequency <= frequencies[0]:
        return values[0]
    if frequency >= frequencies[-1]:
        return values[-1]
    for index in range(1, len(frequencies)):
        if frequencies[index] >= frequency:
            lower_f, upper_f = frequencies[index - 1], frequencies[index]
            lower_v, upper_v = values[index - 1], values[index]
            ratio = (frequency - lower_f) / max(upper_f - lower_f, 1e-12)
            return lower_v + ratio * (upper_v - lower_v)
    return values[-1]


def _pair_peaks(
    a_peaks: Sequence[Mapping[str, float]], b_peaks: Sequence[Mapping[str, float]], threshold_hz: float
) -> Tuple[List[Dict[str, Any]], List[Dict[str, float]], List[Dict[str, float]]]:
    unused_b = list(b_peaks)
    pairs = []
    unpaired_a = []
    for a_peak in a_peaks:
        best = min(unused_b, key=lambda peak: abs(peak["frequency_hz"] - a_peak["frequency_hz"]), default=None)
        if best is None or abs(best["frequency_hz"] - a_peak["frequency_hz"]) > threshold_hz:
            unpaired_a.append(dict(a_peak))
            continue
        unused_b.remove(best)
        pairs.append(
            {
                "a_frequency_hz": a_peak["frequency_hz"],
                "b_frequency_hz": best["frequency_hz"],
                "frequency_delta_hz": best["frequency_hz"] - a_peak["frequency_hz"],
                "a_energy": a_peak["energy"],
                "b_energy": best["energy"],
                "amplitude_ratio_b_over_a": best["energy"] / max(a_peak["energy"], 1e-18),
            }
        )
    return pairs, unpaired_a, [dict(peak) for peak in unused_b]


def _comparison_metrics(a_values: Sequence[float], b_values: Sequence[float], diagnostics: List[Dict[str, Any]]) -> Dict[str, Any]:
    area_a = sum(abs(value) for value in a_values)
    area_b = sum(abs(value) for value in b_values)
    normalized_area_difference = abs(area_a - area_b) / max(area_a + area_b, 1e-18)
    correlation = _correlation(a_values, b_values)
    metrics = {"normalized_area_difference": normalized_area_difference}
    if correlation is None:
        diagnostics.append(_diagnostic("correlation_unavailable", "correlation cannot be computed for constant or non-finite PSD arrays"))
        metrics["correlation"] = {"status": "unavailable"}
    else:
        metrics["correlation"] = {"status": "valid", "value": correlation}
    return metrics


def _correlation(a_values: Sequence[float], b_values: Sequence[float]) -> Optional[float]:
    if len(a_values) != len(b_values) or not a_values:
        return None
    if any(not math.isfinite(value) for value in list(a_values) + list(b_values)):
        return None
    mean_a = sum(a_values) / len(a_values)
    mean_b = sum(b_values) / len(b_values)
    da = [value - mean_a for value in a_values]
    db = [value - mean_b for value in b_values]
    denom_a = math.sqrt(sum(value * value for value in da))
    denom_b = math.sqrt(sum(value * value for value in db))
    if denom_a == 0 or denom_b == 0:
        return None
    return sum(x * y for x, y in zip(da, db)) / (denom_a * denom_b)


def _aliasing_warnings(
    blocks: Mapping[str, MeasurementBlock], path_results: Mapping[str, Mapping[str, Any]], warnings: List[Dict[str, Any]]
) -> None:
    for path, measurement in blocks.items():
        sample_rate = path_results.get(path, {}).get("sample_rate_hz")
        peaks = path_results.get(path, {}).get("peaks", [])
        if sample_rate and peaks and "lis2dw" in measurement.sensor.lower() and peaks[0]["frequency_hz"] > sample_rate * 0.35:
            warnings.append(_warning("aliasing_risk", "LIS2DW sample rate leaves limited margin above detected belt-path peak", path=path))


def _derive_sample_rate(samples: Sequence[Any]) -> Optional[float]:
    if len(samples) < 2:
        return None
    duration = samples[-1].time - samples[0].time
    if duration <= 0:
        return None
    return (len(samples) - 1) / duration


def _motor_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("motor_metadata", "closed_loop_motor_metadata", "qidi_closed_loop_motors", "motors"):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _write_outputs(output_dir: Path, analysis: Dict[str, Any], options: BeltAnalysisOptions, blocked: bool) -> BeltAnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis["blocked"] = blocked
    analysis["comparison_valid"] = not blocked and analysis.get("comparison", {}).get("status") == "comparison_valid"
    graph_paths: List[str] = []
    if options.graphs_enabled and analysis.get("comparison"):
        graphs_dir = output_dir / "graphs"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        overlay = graphs_dir / "belt-psd-overlay.svg"
        _write_overlay_graph(overlay, analysis["paths"])
        graph_paths.append(str(overlay))
        pairs = graphs_dir / "belt-peak-pairs.svg"
        _write_pair_graph(pairs, analysis["comparison"].get("paired_peaks", []))
        graph_paths.append(str(pairs))
    summary_path = None
    if not options.json_only:
        summary = output_dir / "summary.txt"
        summary.write_text(_summary_text(analysis), encoding="utf-8")
        summary_path = str(summary)
    analysis_path = output_dir / "analysis-belts.json"
    analysis_path.write_text(json.dumps(_json_safe(analysis), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return BeltAnalysisResult(str(output_dir), str(analysis_path), summary_path, tuple(graph_paths), blocked, bool(analysis["comparison_valid"]))


def _write_overlay_graph(path: Path, paths: Mapping[str, Mapping[str, Any]]) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200"><text x="20" y="40">A/B PSD overlay</text></svg>\n',
        encoding="utf-8",
    )


def _write_pair_graph(path: Path, pairs: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200"><text x="20" y="40">paired peaks: {len(pairs)}</text></svg>\n',
        encoding="utf-8",
    )


def _summary_text(analysis: Mapping[str, Any]) -> str:
    lines = [f"Source capture: {analysis.get('source_capture')}", ""]
    comparison = analysis.get("comparison", {})
    if comparison:
        lines.append("Comparison: valid")
        metrics = comparison.get("metrics", {})
        lines.append(f"Normalized area difference: {metrics.get('normalized_area_difference')}")
        lines.append(f"Correlation: {metrics.get('correlation')}")
        lines.append(f"Paired peaks: {len(comparison.get('paired_peaks', []))}")
    else:
        lines.append("Comparison: unavailable")
    if analysis.get("motor_metadata"):
        lines.append("Motor metadata:")
        lines.append(json.dumps(analysis["motor_metadata"], sort_keys=True))
    if analysis.get("warnings"):
        lines.append("Warnings:")
        for warning in analysis["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    if analysis.get("diagnostics"):
        lines.append("Diagnostics:")
        for diagnostic in analysis["diagnostics"]:
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
    return "\n".join(lines) + "\n"


def _validation_to_dict(validation: Any) -> Dict[str, Any]:
    return {
        "valid": validation.valid,
        "status": validation.status,
        "diagnostics": [
            {
                "code": diagnostic.status_code,
                "message": diagnostic.message,
                "field_path": diagnostic.field_path,
                "measurement_name": diagnostic.measurement_name,
            }
            for diagnostic in validation.diagnostics
        ],
    }


def _diagnostic(code: str, message: str, path: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "path": path}


def _warning(code: str, message: str, path: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "path": path}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
