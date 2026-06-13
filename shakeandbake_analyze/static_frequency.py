from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import MeasurementBlock, read_capture_artifact

from .shaper import _center_samples, _json_safe, _welch_psd


@dataclass(frozen=True)
class StaticFrequencyAnalysisOptions:
    graphs_enabled: bool = True
    json_only: bool = False
    segment_seconds: float = 0.25
    min_frequency_hz: float = 1.0
    max_frequency_hz: float = 250.0


@dataclass(frozen=True)
class StaticFrequencyAnalysisResult:
    output_dir: str
    analysis_path: str
    summary_path: Optional[str]
    graph_paths: Tuple[str, ...]
    blocked: bool
    analysis_valid: bool


def analyze_static_frequency_capture(
    capture_file: str | Path,
    output_dir: str | Path,
    options: StaticFrequencyAnalysisOptions | None = None,
) -> StaticFrequencyAnalysisResult:
    options = options or StaticFrequencyAnalysisOptions()
    capture_path = Path(capture_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    diagnostics: List[Dict[str, Any]] = []
    analysis: Dict[str, Any] = {
        "source_capture": str(capture_path),
        "source_fingerprint": _sha256(capture_path) if capture_path.exists() else None,
        "validation": {"valid": False, "status": "not_run", "diagnostics": []},
        "diagnostics": diagnostics,
        "warnings": [],
        "static_frequency": {},
    }
    read_result = read_capture_artifact(capture_path)
    analysis["validation"] = _validation_to_dict(read_result.validation)
    if read_result.artifact is None or not read_result.validation.valid:
        diagnostics.extend(analysis["validation"]["diagnostics"])
        return _write_outputs(output_path, analysis, options, blocked=True)
    artifact = read_result.artifact
    if artifact.tool != "static-frequency" and artifact.command != "SHAKEANDBAKE_EXCITE":
        diagnostics.append(_diagnostic("invalid_tool", "capture is not a static-frequency artifact"))
        return _write_outputs(output_path, analysis, options, blocked=True)
    if not artifact.measurements:
        diagnostics.append(_diagnostic("missing_measurement", "static-frequency capture has no measurement block"))
        return _write_outputs(output_path, analysis, options, blocked=True)
    measurement = artifact.measurements[0]
    axis_label = str(measurement.metadata.get("axis_label", measurement.axis)).upper()
    if axis_label not in ("X", "Y", "A", "B"):
        diagnostics.append(_diagnostic("unsupported_axis", "static-frequency analysis supports X, Y, A, and B only", axis_label))
        return _write_outputs(output_path, analysis, options, blocked=True)
    sample_rate = _sample_rate(measurement)
    if sample_rate is None:
        diagnostics.append(_diagnostic("invalid_sample_rate", "sample rate cannot be derived from timestamps", axis_label))
        return _write_outputs(output_path, analysis, options, blocked=True)
    centered = _center_samples(measurement.samples)
    spectrogram = _spectrogram(centered, sample_rate, options)
    cumulative = _cumulative_energy(centered, measurement.samples)
    if not spectrogram["frames"] or not cumulative:
        diagnostics.append(_diagnostic("insufficient_samples", "not enough samples for static-frequency analysis", axis_label))
        return _write_outputs(output_path, analysis, options, blocked=True)
    analysis["static_frequency"] = {
        "axis_label": axis_label,
        "direction_vector": measurement.metadata.get("direction_vector"),
        "frequency": measurement.metadata.get("frequency"),
        "duration": measurement.metadata.get("duration"),
        "sample_rate_hz": sample_rate,
        "spectrogram": spectrogram,
        "cumulative_energy": cumulative,
    }
    return _write_outputs(output_path, analysis, options, blocked=False)


def _spectrogram(values: Sequence[float], sample_rate: float, options: StaticFrequencyAnalysisOptions) -> Dict[str, Any]:
    segment_length = max(16, int(sample_rate * options.segment_seconds))
    segment_length = min(segment_length, len(values))
    if segment_length < 16:
        return {"frames": [], "metadata": {"segment_length": segment_length}}
    step = max(1, segment_length // 2)
    frames = []
    for start in range(0, len(values) - segment_length + 1, step):
        segment = values[start : start + segment_length]
        freqs, psd, metadata = _welch_psd(segment, sample_rate, options)  # type: ignore[arg-type]
        if freqs and psd:
            peak_index = max(range(len(psd)), key=lambda index: psd[index])
            frames.append(
                {
                    "time_start": start / sample_rate,
                    "time_end": (start + segment_length) / sample_rate,
                    "peak_frequency_hz": freqs[peak_index],
                    "energy": sum(psd),
                }
            )
    return {"frames": frames, "metadata": {"segment_length": segment_length, "overlap": segment_length - step}}


def _cumulative_energy(values: Sequence[float], samples: Sequence[Any]) -> List[Dict[str, float]]:
    total = 0.0
    result = []
    for value, sample in zip(values, samples):
        total += value * value
        result.append({"time": sample.time, "energy": total})
    return result


def _sample_rate(measurement: MeasurementBlock) -> Optional[float]:
    samples = measurement.samples
    if len(samples) < 2:
        return None
    duration = samples[-1].time - samples[0].time
    if duration <= 0:
        return None
    return (len(samples) - 1) / duration


def _write_outputs(
    output_dir: Path, analysis: Dict[str, Any], options: StaticFrequencyAnalysisOptions, blocked: bool
) -> StaticFrequencyAnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis["blocked"] = blocked
    analysis["analysis_valid"] = not blocked and bool(analysis.get("static_frequency"))
    graph_paths: List[str] = []
    if options.graphs_enabled and analysis["analysis_valid"]:
        graphs_dir = output_dir / "graphs"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        spectrogram = graphs_dir / "static-frequency-spectrogram.svg"
        spectrogram.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200"><text x="20" y="40">static-frequency spectrogram</text></svg>\n', encoding="utf-8")
        graph_paths.append(str(spectrogram))
        energy = graphs_dir / "static-frequency-energy.svg"
        energy.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200"><text x="20" y="40">cumulative energy</text></svg>\n', encoding="utf-8")
        graph_paths.append(str(energy))
    summary_path = None
    if not options.json_only:
        summary = output_dir / "summary.txt"
        summary.write_text(_summary_text(analysis), encoding="utf-8")
        summary_path = str(summary)
    analysis_path = output_dir / "analysis-static-frequency.json"
    analysis_path.write_text(json.dumps(_json_safe(analysis), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StaticFrequencyAnalysisResult(str(output_dir), str(analysis_path), summary_path, tuple(graph_paths), blocked, bool(analysis["analysis_valid"]))


def _summary_text(analysis: Mapping[str, Any]) -> str:
    lines = [f"Source capture: {analysis.get('source_capture')}", ""]
    if analysis.get("analysis_valid"):
        data = analysis["static_frequency"]
        lines.append(f"Axis: {data.get('axis_label')}")
        lines.append(f"Frequency: {data.get('frequency')}")
        lines.append(f"Duration: {data.get('duration')}")
        lines.append(f"Spectrogram frames: {len(data.get('spectrogram', {}).get('frames', []))}")
    else:
        lines.append("Static-frequency analysis unavailable")
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


def _diagnostic(code: str, message: str, axis: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "axis": axis}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
