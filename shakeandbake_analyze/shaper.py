from __future__ import annotations

import cmath
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import CaptureArtifact, MeasurementBlock, Sample, read_capture_artifact

SHAPER_CANDIDATES = {
    "zv": {"residual_factor": 0.32, "smoothing": 0.10},
    "mzv": {"residual_factor": 0.22, "smoothing": 0.18},
    "ei": {"residual_factor": 0.12, "smoothing": 0.28},
    "2hump_ei": {"residual_factor": 0.08, "smoothing": 0.42},
    "3hump_ei": {"residual_factor": 0.05, "smoothing": 0.58},
}


@dataclass(frozen=True)
class ShaperAnalysisOptions:
    max_smoothing: float = 0.35
    residual_vibration_threshold: float = 0.25
    graphs_enabled: bool = True
    json_only: bool = False
    min_frequency_hz: float = 5.0
    max_frequency_hz: float = 140.0
    peak_relative_threshold: float = 0.25
    peak_absolute_threshold: float = 1e-12


@dataclass(frozen=True)
class ShaperAnalysisResult:
    output_dir: str
    analysis_path: str
    summary_path: Optional[str]
    proposed_config_path: Optional[str]
    graph_paths: Tuple[str, ...]
    blocked: bool
    recommendations_available: bool


def analyze_shaper_capture(
    capture_file: str | Path,
    output_dir: str | Path,
    options: ShaperAnalysisOptions | None = None,
) -> ShaperAnalysisResult:
    options = options or ShaperAnalysisOptions()
    capture_path = Path(capture_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    diagnostics: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    analysis: Dict[str, Any] = {
        "source_capture": str(capture_path),
        "source_fingerprint": _sha256(capture_path) if capture_path.exists() else None,
        "validation": {"valid": False, "status": "not_run", "diagnostics": []},
        "axes": {},
        "warnings": warnings,
        "diagnostics": diagnostics,
        "recommendations": {},
    }

    read_result = read_capture_artifact(capture_path)
    analysis["validation"] = _validation_to_dict(read_result.validation)
    if read_result.artifact is None or not read_result.validation.valid:
        diagnostics.extend(analysis["validation"]["diagnostics"])
        return _write_outputs(output_path, analysis, options, blocked=True)

    artifact = read_result.artifact
    axis_blocks = _select_axis_blocks(artifact, diagnostics)
    if not axis_blocks:
        diagnostics.append(_diagnostic("missing_axis_blocks", "capture contains no valid X or Y measurement blocks"))
        return _write_outputs(output_path, analysis, options, blocked=True)

    for axis, measurement in axis_blocks.items():
        axis_result = _analyze_axis(axis, measurement, options, warnings, diagnostics)
        analysis["axes"][axis] = axis_result
        recommendation = axis_result.get("recommendation")
        if recommendation:
            analysis["recommendations"][axis] = recommendation

    blocked = not analysis["recommendations"]
    if blocked:
        diagnostics.append(_diagnostic("recommendation_unavailable", "no axis produced a valid shaper recommendation"))
    return _write_outputs(output_path, analysis, options, blocked=blocked)


def _select_axis_blocks(artifact: CaptureArtifact, diagnostics: List[Dict[str, Any]]) -> Dict[str, MeasurementBlock]:
    blocks: Dict[str, MeasurementBlock] = {}
    for measurement in artifact.measurements:
        axis = measurement.axis.lower()
        if axis == "z":
            diagnostics.append(
                _diagnostic(
                    "z_axis_ignored",
                    "Max 4 shaper analysis supports X and Y only; Z-labeled measurement ignored",
                    measurement.name,
                )
            )
            continue
        if axis in ("x", "y") and axis not in blocks:
            blocks[axis] = measurement
    return blocks


def _analyze_axis(
    axis: str,
    measurement: MeasurementBlock,
    options: ShaperAnalysisOptions,
    warnings: List[Dict[str, Any]],
    diagnostics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    samples = measurement.samples
    sample_rate = _derive_sample_rate(samples)
    if sample_rate is None:
        diagnostics.append(_diagnostic("sample_rate_unavailable", "sample rate cannot be derived from timestamps", measurement.name))
        return {"valid": False, "measurement": measurement.name}

    centered = _center_samples(samples)
    frequencies, psd_values, metadata = _welch_psd(centered, sample_rate, options)
    axis_result: Dict[str, Any] = {
        "valid": False,
        "measurement": measurement.name,
        "sample_rate_hz": sample_rate,
        "frequency_resolution_hz": metadata.get("frequency_resolution_hz"),
        "psd_metadata": metadata,
        "peaks": [],
        "candidates": {},
        "diagnostics": [],
        "warnings": [],
    }

    psd_issue = _validate_psd(frequencies, psd_values)
    if psd_issue:
        diagnostic = _diagnostic(psd_issue, "PSD values are unusable", measurement.name)
        diagnostics.append(diagnostic)
        axis_result["diagnostics"].append(diagnostic)
        return axis_result

    peaks = _detect_peaks(frequencies, psd_values, options)
    axis_result["peaks"] = peaks
    if not peaks:
        diagnostic = _diagnostic("no_resonance_peak", "no resonance peak exceeded detection thresholds", measurement.name)
        diagnostics.append(diagnostic)
        axis_result["diagnostics"].append(diagnostic)
        return axis_result

    dominant = peaks[0]
    damping = _estimate_damping(frequencies, psd_values, dominant["frequency_hz"])
    axis_result["damping"] = damping
    if damping.get("status") != "valid":
        diagnostic = _diagnostic("damping_unavailable", damping.get("reason", "half-power crossings unavailable"), measurement.name)
        diagnostics.append(diagnostic)
        axis_result["diagnostics"].append(diagnostic)

    axis_warnings = _signal_warnings(measurement, sample_rate, psd_values, dominant)
    warnings.extend(axis_warnings)
    axis_result["warnings"].extend(axis_warnings)

    candidates = _evaluate_candidates(dominant, options)
    axis_result["candidates"] = candidates
    recommendation = _select_recommendations(candidates, options)
    if recommendation is None:
        diagnostic = _diagnostic("candidate_constraints_unsatisfied", "no candidate satisfied configured constraints", measurement.name)
        diagnostics.append(diagnostic)
        axis_result["diagnostics"].append(diagnostic)
    else:
        axis_result["recommendation"] = recommendation
        axis_result["valid"] = True
    axis_result["psd"] = {"frequencies_hz": frequencies, "values": psd_values}
    return axis_result


def _derive_sample_rate(samples: Sequence[Sample]) -> Optional[float]:
    if len(samples) < 2:
        return None
    duration = samples[-1].time - samples[0].time
    if duration <= 0:
        return None
    return (len(samples) - 1) / duration


def _center_samples(samples: Sequence[Sample]) -> List[float]:
    channels = [
        [sample.accel_x for sample in samples],
        [sample.accel_y for sample in samples],
        [sample.accel_z for sample in samples],
    ]
    centered = [[value - median(channel) for value in channel] for channel in channels]
    return max(centered, key=lambda channel: sum(value * value for value in channel))


def _welch_psd(values: Sequence[float], sample_rate: float, options: ShaperAnalysisOptions) -> Tuple[List[float], List[float], Dict[str, Any]]:
    segment_length = min(256, _largest_power_of_two(len(values)))
    if segment_length < 8:
        return [], [], {"window": "hann", "segment_length": segment_length, "overlap": 0}
    overlap = segment_length // 2
    step = max(1, segment_length - overlap)
    window = _hann(segment_length)
    window_power = sum(item * item for item in window) or 1.0
    bins = segment_length // 2 + 1
    accum = [0.0] * bins
    count = 0
    for start in range(0, len(values) - segment_length + 1, step):
        segment = [(values[start + index]) * window[index] for index in range(segment_length)]
        spectrum = _dft(segment)
        for index in range(bins):
            power = (abs(spectrum[index]) ** 2) / (sample_rate * window_power)
            accum[index] += power
        count += 1
    if count == 0:
        return [], [], {"window": "hann", "segment_length": segment_length, "overlap": overlap}
    frequencies = [sample_rate * index / segment_length for index in range(bins)]
    psd = [value / count for value in accum]
    filtered = [(f, p) for f, p in zip(frequencies, psd) if options.min_frequency_hz <= f <= options.max_frequency_hz]
    if not filtered:
        return [], [], {"window": "hann", "segment_length": segment_length, "overlap": overlap}
    frequencies, psd = zip(*filtered)
    return list(frequencies), list(psd), {
        "method": "welch",
        "window": "hann",
        "segment_length": segment_length,
        "overlap": overlap,
        "frequency_min_hz": options.min_frequency_hz,
        "frequency_max_hz": options.max_frequency_hz,
        "frequency_resolution_hz": sample_rate / segment_length,
    }


def _dft(values: Sequence[float]) -> List[complex]:
    size = len(values)
    return [sum(value * cmath.exp(-2j * math.pi * k * n / size) for n, value in enumerate(values)) for k in range(size)]


def _hann(size: int) -> List[float]:
    if size <= 1:
        return [1.0]
    return [0.5 - 0.5 * math.cos(2 * math.pi * index / (size - 1)) for index in range(size)]


def _largest_power_of_two(value: int) -> int:
    power = 1
    while power * 2 <= value:
        power *= 2
    return power


def _validate_psd(frequencies: Sequence[float], values: Sequence[float]) -> Optional[str]:
    if not frequencies or not values:
        return "invalid_psd_empty"
    if any(not math.isfinite(value) for value in values):
        return "invalid_psd_nonfinite"
    if all(value == 0 for value in values):
        return "invalid_psd_zero"
    if len({round(value, 18) for value in values}) <= 1:
        return "invalid_psd_constant"
    return None


def _detect_peaks(frequencies: Sequence[float], values: Sequence[float], options: ShaperAnalysisOptions) -> List[Dict[str, float]]:
    max_value = max(values)
    threshold = max(options.peak_absolute_threshold, max_value * options.peak_relative_threshold)
    peaks = []
    for index in range(1, len(values) - 1):
        value = values[index]
        if value < threshold or value < values[index - 1] or value < values[index + 1]:
            continue
        prominence = value - max(values[index - 1], values[index + 1])
        peaks.append({"frequency_hz": frequencies[index], "energy": value, "prominence": prominence})
    return sorted(peaks, key=lambda item: item["energy"], reverse=True)


def _estimate_damping(frequencies: Sequence[float], values: Sequence[float], peak_frequency: float) -> Dict[str, Any]:
    if not frequencies:
        return {"status": "unavailable", "reason": "empty PSD"}
    peak_index = min(range(len(frequencies)), key=lambda index: abs(frequencies[index] - peak_frequency))
    peak_value = values[peak_index]
    half_power = peak_value / 2.0
    lower = None
    for index in range(peak_index - 1, -1, -1):
        if values[index] <= half_power:
            lower = frequencies[index]
            break
    upper = None
    for index in range(peak_index + 1, len(values)):
        if values[index] <= half_power:
            upper = frequencies[index]
            break
    if lower is None or upper is None or peak_frequency <= 0 or upper <= lower:
        return {"status": "unavailable", "reason": "valid half-power crossings not found", "half_power": half_power}
    return {
        "status": "valid",
        "ratio": (upper - lower) / (2.0 * peak_frequency),
        "half_power": half_power,
        "lower_hz": lower,
        "upper_hz": upper,
    }


def _evaluate_candidates(dominant: Mapping[str, float], options: ShaperAnalysisOptions) -> Dict[str, Dict[str, float]]:
    peak_hz = dominant["frequency_hz"]
    energy = max(dominant["energy"], options.peak_absolute_threshold)
    prominence = max(dominant["prominence"], 0.0)
    prominence_ratio = min(1.0, prominence / energy) if energy else 0.0
    candidates = {}
    for name, definition in SHAPER_CANDIDATES.items():
        residual = definition["residual_factor"] * (1.0 - 0.5 * prominence_ratio)
        smoothing = definition["smoothing"] * (50.0 / max(peak_hz, 1.0))
        acceleration = 20000.0 / (1.0 + smoothing * 8.0)
        candidates[name] = {
            "frequency_hz": peak_hz,
            "residual_vibration": residual,
            "smoothing": smoothing,
            "accel_per_hz_guidance": acceleration,
        }
    return candidates


def _select_recommendations(
    candidates: Mapping[str, Mapping[str, float]], options: ShaperAnalysisOptions
) -> Optional[Dict[str, Any]]:
    viable = [
        (name, metrics)
        for name, metrics in candidates.items()
        if all(math.isfinite(value) for value in metrics.values())
        and metrics["residual_vibration"] <= options.residual_vibration_threshold
        and metrics["smoothing"] <= options.max_smoothing
    ]
    if not viable:
        return None
    low_vibration = min(viable, key=lambda item: item[1]["residual_vibration"])
    performance = max(viable, key=lambda item: item[1]["accel_per_hz_guidance"])
    selected = low_vibration
    return {
        "selected_shaper": selected[0],
        "frequency_hz": selected[1]["frequency_hz"],
        "residual_vibration": selected[1]["residual_vibration"],
        "smoothing": selected[1]["smoothing"],
        "accel_per_hz_guidance": selected[1]["accel_per_hz_guidance"],
        "low_vibration_candidate": low_vibration[0],
        "performance_candidate": performance[0],
    }


def _signal_warnings(
    measurement: MeasurementBlock, sample_rate: float, psd_values: Sequence[float], dominant: Mapping[str, float]
) -> List[Dict[str, Any]]:
    warnings = []
    sensor = measurement.sensor.lower()
    if "lis2dw" not in sensor:
        return warnings
    peak_frequency = dominant["frequency_hz"]
    if sample_rate < 500 or peak_frequency > sample_rate * 0.35:
        warnings.append(_warning("aliasing_risk", "LIS2DW sample rate leaves limited margin above detected resonance", measurement.name))
    sorted_values = sorted(psd_values)
    noise_floor = sorted_values[len(sorted_values) // 2]
    if noise_floor > 0 and dominant["energy"] / noise_floor < 3.0:
        warnings.append(_warning("excessive_noise", "PSD peak is close to the estimated noise floor", measurement.name))
    if dominant["energy"] < 1e-8:
        warnings.append(_warning("insufficient_signal", "dominant resonance energy is very low", measurement.name))
    return warnings


def _write_outputs(
    output_dir: Path, analysis: Dict[str, Any], options: ShaperAnalysisOptions, blocked: bool
) -> ShaperAnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = output_dir / "analysis-shaper.json"
    graph_paths: List[str] = []
    recommendations = analysis.get("recommendations", {})
    analysis["blocked"] = blocked
    analysis["recommendations_available"] = bool(recommendations)

    if options.graphs_enabled:
        graphs_dir = output_dir / "graphs"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        for axis, axis_result in analysis.get("axes", {}).items():
            psd = axis_result.get("psd")
            if psd:
                graph = graphs_dir / f"{axis}-psd.svg"
                _write_svg_graph(graph, psd["frequencies_hz"], psd["values"], f"{axis.upper()} PSD")
                graph_paths.append(str(graph))
        if recommendations:
            graph = graphs_dir / "candidate-summary.svg"
            _write_candidate_graph(graph, analysis.get("axes", {}))
            graph_paths.append(str(graph))

    summary_path = None
    if not options.json_only:
        summary = output_dir / "summary.txt"
        summary.write_text(_summary_text(analysis), encoding="utf-8")
        summary_path = str(summary)

    proposed_path = None
    if recommendations:
        proposed = output_dir / "input-shaper.proposed.cfg"
        proposed.write_text(_proposed_config(recommendations), encoding="utf-8")
        proposed_path = str(proposed)

    analysis_path.write_text(json.dumps(_json_safe(analysis), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ShaperAnalysisResult(
        output_dir=str(output_dir),
        analysis_path=str(analysis_path),
        summary_path=summary_path,
        proposed_config_path=proposed_path,
        graph_paths=tuple(graph_paths),
        blocked=blocked,
        recommendations_available=bool(recommendations),
    )


def _write_svg_graph(path: Path, frequencies: Sequence[float], values: Sequence[float], title: str) -> None:
    width, height = 640, 320
    max_value = max(values) if values else 1.0
    min_frequency = min(frequencies) if frequencies else 0.0
    max_frequency = max(frequencies) if frequencies else 1.0
    points = []
    for frequency, value in zip(frequencies, values):
        x = 40 + (frequency - min_frequency) / max(max_frequency - min_frequency, 1e-9) * (width - 60)
        y = height - 30 - value / max(max_value, 1e-18) * (height - 60)
        points.append(f"{x:.1f},{y:.1f}")
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<text x="20" y="24">{title}</text><polyline fill="none" stroke="black" points="{" ".join(points)}"/></svg>\n',
        encoding="utf-8",
    )


def _write_candidate_graph(path: Path, axes: Mapping[str, Mapping[str, Any]]) -> None:
    labels = []
    for axis, result in axes.items():
        rec = result.get("recommendation")
        if rec:
            labels.append(f"{axis.upper()}: {rec['selected_shaper']} @ {rec['frequency_hz']:.1f} Hz")
    text = " | ".join(labels) or "No recommendations"
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="120"><text x="20" y="60">{text}</text></svg>\n', encoding="utf-8")


def _summary_text(analysis: Mapping[str, Any]) -> str:
    lines = [f"Source capture: {analysis.get('source_capture')}", ""]
    for axis, result in analysis.get("axes", {}).items():
        lines.append(f"## Axis {axis.upper()}")
        lines.append(f"Sample rate: {result.get('sample_rate_hz')} Hz")
        rec = result.get("recommendation")
        if rec:
            lines.append(f"Recommendation: {rec['selected_shaper']} @ {rec['frequency_hz']:.2f} Hz")
        else:
            lines.append("Recommendation: unavailable")
        lines.append("")
    if analysis.get("warnings"):
        lines.append("Warnings:")
        for warning in analysis["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    if analysis.get("diagnostics"):
        lines.append("Diagnostics:")
        for diagnostic in analysis["diagnostics"]:
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
    return "\n".join(lines) + "\n"


def _proposed_config(recommendations: Mapping[str, Mapping[str, Any]]) -> str:
    lines = ["[input_shaper]"]
    for axis in ("x", "y"):
        rec = recommendations.get(axis)
        if rec:
            lines.append(f"shaper_type_{axis}: {rec['selected_shaper']}")
            lines.append(f"shaper_freq_{axis}: {rec['frequency_hz']:.2f}")
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


def _diagnostic(code: str, message: str, measurement: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "measurement": measurement}


def _warning(code: str, message: str, measurement: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "measurement": measurement}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None
    return value
