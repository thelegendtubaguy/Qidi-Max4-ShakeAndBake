from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import (
    MeasurementBlock,
    SPEED_LIMIT_COMMAND,
    SPEED_LIMIT_METADATA_KEY,
    read_capture_artifact,
)

from .shaper import _center_samples, _json_safe, _validate_psd, _welch_psd


@dataclass(frozen=True)
class SpeedLimitAnalysisOptions:
    graphs_enabled: bool = True
    json_only: bool = False
    summary_only: bool = False
    min_frequency_hz: float = 5.0
    max_frequency_hz: float = 140.0
    angular_resolution_degrees: float = 15.0
    avoid_peak_relative_threshold: float = 0.25
    avoid_margin_speed: float = 20.0
    preferred_relative_threshold: float = 0.60
    preferred_min_width: float = 20.0
    derate: float = 0.85


@dataclass(frozen=True)
class SpeedLimitAnalysisResult:
    output_dir: str
    analysis_path: str
    summary_path: Optional[str]
    proposed_config_path: Optional[str]
    proposed_slicer_path: Optional[str]
    graph_paths: Tuple[str, ...]
    blocked: bool
    recommendations_available: bool


def analyze_speed_limit_capture(
    capture_file: str | Path,
    output_dir: str | Path,
    options: SpeedLimitAnalysisOptions | None = None,
) -> SpeedLimitAnalysisResult:
    options = options or SpeedLimitAnalysisOptions()
    capture_path = Path(capture_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    diagnostics: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    analysis: Dict[str, Any] = {
        "source_capture": str(capture_path),
        "source_fingerprint": _sha256(capture_path) if capture_path.exists() else None,
        "validation": {"valid": False, "status": "not_run", "diagnostics": []},
        "diagnostics": diagnostics,
        "warnings": warnings,
        "motion_limits": {},
        "shaper": {},
        "speed_profile": {},
        "recommendations": {},
    }

    read_result = read_capture_artifact(capture_path)
    analysis["validation"] = _validation_to_dict(read_result.validation)
    if read_result.artifact is None or not read_result.validation.valid:
        diagnostics.extend(analysis["validation"]["diagnostics"])
        return _write_outputs(output_path, analysis, options, blocked=True)

    artifact = read_result.artifact
    if artifact.command != SPEED_LIMIT_COMMAND:
        diagnostics.append(_diagnostic("wrong_command", f"capture command is not {SPEED_LIMIT_COMMAND}"))
        return _write_outputs(output_path, analysis, options, blocked=True)

    evidence = artifact.metadata.get(SPEED_LIMIT_METADATA_KEY)
    if not isinstance(evidence, Mapping):
        diagnostics.append(_diagnostic("missing_speed_limit_metadata", "speed-limit metadata is missing"))
        return _write_outputs(output_path, analysis, options, blocked=True)

    _validate_speed_limit_evidence(evidence, diagnostics)
    candidate_analysis = _classify_candidates(evidence, diagnostics)
    analysis["motion_limits"] = candidate_analysis

    shaper = _shaper_evidence(artifact.measurements, diagnostics)
    analysis["shaper"] = shaper
    speed_profile = _analyze_speed_profile(artifact.measurements, evidence, options, diagnostics, warnings)
    analysis["speed_profile"] = speed_profile

    recommendations = _recommend(candidate_analysis, shaper, speed_profile, artifact.metadata, options, diagnostics)
    analysis["recommendations"] = recommendations
    blocked = not bool(recommendations)
    if blocked:
        diagnostics.append(_diagnostic("recommendation_unavailable", "speed-limit recommendations are unavailable"))
    return _write_outputs(output_path, analysis, options, blocked=blocked)


def _validate_speed_limit_evidence(evidence: Mapping[str, Any], diagnostics: List[Dict[str, Any]]) -> None:
    for key in ("phases", "candidates", "trigger_observations", "closed_loop_observations", "recommendation_inputs"):
        if key not in evidence:
            diagnostics.append(_diagnostic("missing_speed_limit_field", f"missing speed-limit field: {key}", field=key))
    observations = evidence.get("trigger_observations", [])
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes, bytearray)) or not observations:
        diagnostics.append(_diagnostic("missing_baseline_evidence", "trigger baseline observations are required"))
    else:
        baseline_axes = {str(item.get("axis", "")).lower() for item in observations if isinstance(item, Mapping) and item.get("phase") == "endstop_baseline" and item.get("available", True)}
        if not {"x", "y"}.issubset(baseline_axes):
            diagnostics.append(_diagnostic("missing_baseline_axis", "X and Y baseline trigger observations are required"))
        for item in observations:
            if isinstance(item, Mapping) and item.get("available") is False:
                diagnostics.append(_diagnostic("trigger_observation_unavailable", "trigger observation is unavailable", axis=item.get("axis")))
    candidates = evidence.get("candidates", [])
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes, bytearray)) or not candidates:
        diagnostics.append(_diagnostic("missing_candidates", "candidate evidence is required"))
    else:
        required = {"candidate_id", "velocity", "acceleration", "directions", "trigger_drift"}
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                diagnostics.append(_diagnostic("malformed_candidate", "candidate record must be an object"))
                continue
            missing = sorted(field for field in required if field not in candidate)
            if missing:
                diagnostics.append(_diagnostic("malformed_candidate", "candidate record is missing fields", candidate.get("candidate_id"), fields=missing))
    for observation in evidence.get("closed_loop_observations", []) or []:
        if isinstance(observation, Mapping) and observation.get("unsafe"):
            diagnostics.append(_diagnostic("closed_loop_unsafe", "closed-loop observation reports an unsafe state", observation.get("candidate_id")))


def _classify_candidates(evidence: Mapping[str, Any], diagnostics: List[Dict[str, Any]]) -> Dict[str, Any]:
    classified = []
    passing = []
    failing = []
    stopped = []
    for candidate in evidence.get("candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = str(candidate.get("candidate_id", ""))
        drifts = [drift for drift in candidate.get("trigger_drift", []) or [] if isinstance(drift, Mapping)]
        safety_stop = candidate.get("safety_stop")
        if safety_stop:
            status = "stopped"
            stopped.append(candidate_id)
        elif drifts and all(bool(drift.get("passed")) for drift in drifts):
            status = "passed"
            passing.append(candidate)
        elif drifts:
            status = "failed"
            failing.append(candidate)
        else:
            status = "unclassified"
            diagnostics.append(_diagnostic("candidate_unclassified", "candidate has no trigger-drift evidence", candidate_id))
        item = dict(candidate)
        item["classification"] = status
        classified.append(item)

    distinct_speeds = sorted({float(item.get("velocity")) for item in classified if _finite(item.get("velocity"))})
    distinct_accels = sorted({float(item.get("acceleration")) for item in classified if _finite(item.get("acceleration"))})
    if len(distinct_speeds) < 2 or len(distinct_accels) < 1:
        diagnostics.append(_diagnostic("insufficient_grid", "candidate grid is sparse; boundary confidence is limited"))

    observed: Dict[str, Any] = {}
    if passing:
        observed = {
            "highest_passing_velocity": max(float(item["velocity"]) for item in passing),
            "highest_passing_acceleration": max(float(item["acceleration"]) for item in passing),
            "passing_envelope": [str(item.get("candidate_id")) for item in passing],
            "first_failing_candidates": [str(item.get("candidate_id")) for item in failing[:3]],
            "stopped_candidate_regions": stopped,
        }
    else:
        diagnostics.append(_diagnostic("no_passing_candidates", "no candidate has enough evidence to be classified as passing"))
    return {
        "classified_candidates": classified,
        "observed_tested_ceilings": observed,
        "passing_count": len(passing),
        "failing_count": len(failing),
        "stopped_count": len(stopped),
    }


def _shaper_evidence(measurements: Sequence[MeasurementBlock], diagnostics: List[Dict[str, Any]]) -> Dict[str, Any]:
    axes = {}
    for measurement in measurements:
        axis = measurement.axis.lower()
        if axis in ("x", "y") and measurement.name.endswith("_shaper"):
            axes[axis] = {"measurement": measurement.name, "sample_count": measurement.effective_sample_count}
    missing = [axis for axis in ("x", "y") if axis not in axes]
    if missing:
        diagnostics.append(_diagnostic("missing_shaper_evidence", "X/Y shaper measurements are required for full recommendations", fields=missing))
    return {"valid": not missing, "axes": axes, "missing_axes": missing}


def _analyze_speed_profile(
    measurements: Sequence[MeasurementBlock],
    evidence: Mapping[str, Any],
    options: SpeedLimitAnalysisOptions,
    diagnostics: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    plan = evidence.get("speed_profile_plan") if isinstance(evidence.get("speed_profile_plan"), Mapping) else {}
    expected_speeds = [float(value) for value in plan.get("speeds", []) if _finite(value)] if isinstance(plan, Mapping) else []
    selected: Dict[Tuple[float, float], MeasurementBlock] = {}
    ignored_z = False
    for measurement in measurements:
        metadata = measurement.metadata
        axis = measurement.axis.lower()
        if axis == "z" or metadata.get("axis_label") == "Z":
            ignored_z = True
            continue
        if metadata.get("kind") != "speed_profile" and not measurement.name.startswith("speed_profile"):
            continue
        speed = metadata.get("speed")
        angle = metadata.get("direction_angle", metadata.get("angle_degrees"))
        if _finite(speed) and _finite(angle):
            selected[(float(speed), float(angle))] = measurement
    if ignored_z:
        diagnostics.append(_diagnostic("z_speed_profile_ignored", "Max 4 speed-profile analysis supports CoreXY X/Y directions only"))
    if not expected_speeds:
        expected_speeds = sorted({speed for speed, _ in selected})
    required_angles = (45.0, 135.0)
    measurement_energy: List[Dict[str, Any]] = []
    energy_by_speed: Dict[float, Dict[float, float]] = {}
    validation_diagnostics: List[Dict[str, Any]] = []
    for speed in expected_speeds:
        for angle in required_angles:
            measurement = selected.get((speed, angle))
            if measurement is None:
                diagnostic = _diagnostic("missing_speed_profile_measurement", "missing required speed/direction measurement", speed=speed, angle=angle)
                diagnostics.append(diagnostic)
                validation_diagnostics.append(diagnostic)
                continue
            result = _measurement_energy(measurement, options)
            measurement_energy.append(result)
            if result.get("valid"):
                energy_by_speed.setdefault(speed, {})[angle] = float(result["energy"])
            else:
                diagnostics.extend(result.get("diagnostics", []))
                validation_diagnostics.extend(result.get("diagnostics", []))
    projection = _project_speed_profile(energy_by_speed, options)
    avoid_bands = _avoid_bands(projection["per_speed"], options)
    preferred = _preferred_ranges(projection["per_speed"], options)
    if not projection["per_speed"]:
        warnings.append(_warning("speed_profile_unavailable", "speed-profile projection is unavailable"))
    return {
        "validation_diagnostics": validation_diagnostics,
        "measurement_energy": measurement_energy,
        "projection": projection,
        "avoid_bands": avoid_bands,
        "preferred_ranges": preferred,
        "angle_summaries": projection.get("angle_summaries", []),
        "warnings": warnings,
    }


def _measurement_energy(measurement: MeasurementBlock, options: SpeedLimitAnalysisOptions) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "valid": False,
        "measurement": measurement.name,
        "speed": measurement.metadata.get("speed"),
        "direction_angle": measurement.metadata.get("direction_angle"),
        "diagnostics": [],
    }
    sample_rate = _derive_sample_rate(measurement)
    result["sample_rate_hz"] = sample_rate
    if sample_rate is None or sample_rate <= 0:
        result["diagnostics"].append(_diagnostic("invalid_sample_rate", "sample rate is not usable", measurement.name))
        return result
    frequencies, values, metadata = _welch_psd(_center_samples(measurement.samples), sample_rate, _PsdOptions(options))  # type: ignore[arg-type]
    issue = _validate_psd(frequencies, values)
    result["psd_metadata"] = metadata
    if issue:
        result["diagnostics"].append(_diagnostic("degenerate_psd", issue, measurement.name))
        return result
    energy = sum(value for frequency, value in zip(frequencies, values) if options.min_frequency_hz <= frequency <= options.max_frequency_hz)
    result.update({"valid": True, "energy": energy, "frequency_band": [options.min_frequency_hz, options.max_frequency_hz]})
    return result


class _PsdOptions:
    def __init__(self, options: SpeedLimitAnalysisOptions):
        self.min_frequency_hz = options.min_frequency_hz
        self.max_frequency_hz = options.max_frequency_hz
        self.peak_relative_threshold = options.avoid_peak_relative_threshold
        self.peak_absolute_threshold = 1e-12


def _project_speed_profile(energy_by_speed: Mapping[float, Mapping[float, float]], options: SpeedLimitAnalysisOptions) -> Dict[str, Any]:
    step = max(options.angular_resolution_degrees, 1.0)
    angles = []
    angle = 0.0
    while angle < 360.0:
        angles.append(round(angle, 6))
        angle += step
    per_speed = []
    angle_values: Dict[float, List[float]] = {angle: [] for angle in angles}
    for speed in sorted(energy_by_speed):
        directions = energy_by_speed[speed]
        if 45.0 not in directions or 135.0 not in directions:
            continue
        e45 = float(directions[45.0])
        e135 = float(directions[135.0])
        projected = []
        for angle in angles:
            radians = math.radians(angle)
            w45 = abs(math.cos(radians) + math.sin(radians))
            w135 = abs(-math.cos(radians) + math.sin(radians))
            total = w45 + w135 or 1.0
            energy = (e45 * w45 + e135 * w135) / total
            projected.append({"angle_degrees": angle, "energy": energy})
            angle_values[angle].append(energy)
        energies = [item["energy"] for item in projected]
        per_speed.append(
            {
                "speed": speed,
                "projected_energy": projected,
                "minimum": min(energies),
                "maximum": max(energies),
                "variance": _variance(energies),
                "combined_metric": max(energies),
            }
        )
    angle_summaries = [
        {"angle_degrees": angle, "mean_energy": sum(values) / len(values), "sample_count": len(values)}
        for angle, values in angle_values.items()
        if values
    ]
    low_angles = []
    if angle_summaries:
        threshold = min(item["mean_energy"] for item in angle_summaries) * 1.25
        low_angles = [item for item in angle_summaries if item["mean_energy"] <= threshold]
    return {"angular_resolution_degrees": step, "per_speed": per_speed, "angle_summaries": angle_summaries, "low_vibration_angle_ranges": low_angles}


def _avoid_bands(per_speed: Sequence[Mapping[str, Any]], options: SpeedLimitAnalysisOptions) -> List[Dict[str, Any]]:
    if not per_speed:
        return []
    max_metric = max(float(item["combined_metric"]) for item in per_speed)
    threshold = max_metric * options.avoid_peak_relative_threshold
    bands = []
    for item in per_speed:
        metric = float(item["combined_metric"])
        if metric >= threshold and metric == max_metric:
            speed = float(item["speed"])
            bands.append(
                {
                    "speed_min": max(0.0, speed - options.avoid_margin_speed),
                    "speed_max": speed + options.avoid_margin_speed,
                    "peak_speed": speed,
                    "energy": metric,
                    "margin": options.avoid_margin_speed,
                }
            )
    return bands


def _preferred_ranges(per_speed: Sequence[Mapping[str, Any]], options: SpeedLimitAnalysisOptions) -> List[Dict[str, Any]]:
    if not per_speed:
        return []
    metrics = [float(item["combined_metric"]) for item in per_speed]
    threshold = min(metrics) + (max(metrics) - min(metrics)) * options.preferred_relative_threshold
    preferred = [item for item in per_speed if float(item["combined_metric"]) <= threshold]
    if not preferred:
        return []
    speeds = sorted(float(item["speed"]) for item in preferred)
    ranges = []
    start = last = speeds[0]
    spacing = _median_spacing(sorted(float(item["speed"]) for item in per_speed))
    for speed in speeds[1:]:
        if speed - last <= max(spacing * 1.5, 1.0):
            last = speed
            continue
        if last - start >= options.preferred_min_width or start == last:
            ranges.append({"speed_min": start, "speed_max": last, "supporting_metric": threshold})
        start = last = speed
    if last - start >= options.preferred_min_width or start == last:
        ranges.append({"speed_min": start, "speed_max": last, "supporting_metric": threshold})
    return ranges


def _recommend(
    candidate_analysis: Mapping[str, Any],
    shaper: Mapping[str, Any],
    speed_profile: Mapping[str, Any],
    metadata: Mapping[str, Any],
    options: SpeedLimitAnalysisOptions,
    diagnostics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    observed = candidate_analysis.get("observed_tested_ceilings", {})
    if not observed:
        return {}
    if not shaper.get("valid"):
        diagnostics.append(_diagnostic("recommendation_withheld_missing_shaper", "recommended limits require X/Y shaper evidence"))
        return {}
    max_velocity = float(observed["highest_passing_velocity"])
    max_accel = float(observed["highest_passing_acceleration"])
    rec_velocity = max_velocity * options.derate
    rec_accel = max_accel * options.derate
    preferred = speed_profile.get("preferred_ranges", []) if isinstance(speed_profile, Mapping) else []
    slicer_speed = rec_velocity
    if preferred:
        slicer_speed = min(slicer_speed, max(float(item["speed_max"]) for item in preferred))
    avoid_bands = speed_profile.get("avoid_bands", []) if isinstance(speed_profile, Mapping) else []
    for band in avoid_bands:
        if float(band["speed_min"]) <= slicer_speed <= float(band["speed_max"]):
            slicer_speed = max(0.0, float(band["speed_min"]) - 1.0)
    velocity_state = metadata.get("velocity_limit_state", {}) if isinstance(metadata.get("velocity_limit_state"), Mapping) else {}
    configured_max_velocity = velocity_state.get("max_velocity")
    configured_max_accel = velocity_state.get("max_accel")
    if _finite(configured_max_velocity):
        rec_velocity = min(rec_velocity, float(configured_max_velocity))
        slicer_speed = min(slicer_speed, float(configured_max_velocity))
    if _finite(configured_max_accel):
        rec_accel = min(rec_accel, float(configured_max_accel))
    return {
        "max_velocity": {
            "value": rec_velocity,
            "observed_tested_ceiling": max_velocity,
            "derate": options.derate,
            "evidence": ["passing_candidate_envelope", "trigger_drift", "shaper_measurements"],
        },
        "max_accel": {
            "value": rec_accel,
            "observed_tested_ceiling": max_accel,
            "derate": options.derate,
            "evidence": ["passing_candidate_envelope", "trigger_drift", "shaper_measurements"],
        },
        "slicer_motion_speed": {
            "value": slicer_speed,
            "scope": "motion_quality_only",
            "excludes": ["filament", "nozzle", "cooling", "pressure_advance", "extrusion_flow", "material_specific_limits"],
            "evidence": ["passing_candidate_envelope", "speed_profile_vibration"],
        },
    }


def _write_outputs(
    output_dir: Path, analysis: Dict[str, Any], options: SpeedLimitAnalysisOptions, blocked: bool
) -> SpeedLimitAnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis["blocked"] = blocked
    analysis["recommendations_available"] = bool(analysis.get("recommendations"))
    graph_paths: List[str] = []
    if options.graphs_enabled and not options.summary_only:
        try:
            graphs_dir = output_dir / "graphs"
            graphs_dir.mkdir(parents=True, exist_ok=True)
            for name in ("speed-angle-heatmap", "per-speed-energy", "avoid-bands", "preferred-ranges"):
                graph = graphs_dir / f"{name}.svg"
                graph.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200"><text x="20" y="40">{name}</text></svg>\n', encoding="utf-8")
                graph_paths.append(str(graph))
        except OSError as exc:
            analysis.setdefault("diagnostics", []).append(_diagnostic("graph_generation_failed", str(exc)))
    analysis.setdefault("speed_profile", {})["graph_paths"] = graph_paths
    summary_path = None
    if not options.json_only:
        summary = output_dir / "summary.txt"
        summary.write_text(_summary_text(analysis), encoding="utf-8")
        summary_path = str(summary)
    proposed_config_path = None
    proposed_slicer_path = None
    if analysis.get("recommendations"):
        proposed = output_dir / "speed-limits.proposed.cfg"
        proposed.write_text(_proposed_config(analysis["recommendations"]), encoding="utf-8")
        proposed_config_path = str(proposed)
        slicer = output_dir / "slicer-motion-speed.proposed.txt"
        slicer.write_text(_proposed_slicer(analysis["recommendations"]), encoding="utf-8")
        proposed_slicer_path = str(slicer)
    analysis_path = output_dir / "analysis-speed-limits.json"
    analysis_path.write_text(json.dumps(_json_safe(analysis), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return SpeedLimitAnalysisResult(
        str(output_dir),
        str(analysis_path),
        summary_path,
        proposed_config_path,
        proposed_slicer_path,
        tuple(graph_paths),
        blocked,
        bool(analysis.get("recommendations")),
    )


def _summary_text(analysis: Mapping[str, Any]) -> str:
    lines = [f"Source capture: {analysis.get('source_capture')}", ""]
    observed = analysis.get("motion_limits", {}).get("observed_tested_ceilings", {})
    if observed:
        lines.append("Observed tested ceilings:")
        lines.append(f"- max_velocity: {observed.get('highest_passing_velocity')}")
        lines.append(f"- max_accel: {observed.get('highest_passing_acceleration')}")
    else:
        lines.append("Observed tested ceilings: unavailable")
    recs = analysis.get("recommendations", {})
    if recs:
        lines.append("Recommended limits:")
        for key, value in recs.items():
            lines.append(f"- {key}: {value.get('value')}")
        lines.append("Slicer speed guidance is motion-quality guidance only; it excludes filament, nozzle, cooling, pressure advance, extrusion flow, and material-specific limits.")
    else:
        lines.append("Recommended limits: unavailable")
    if analysis.get("diagnostics"):
        lines.append("Diagnostics:")
        for diagnostic in analysis["diagnostics"]:
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
    return "\n".join(lines) + "\n"


def _proposed_config(recommendations: Mapping[str, Mapping[str, Any]]) -> str:
    lines = ["# Operator-applied Shake&Bake recommendation", "[printer]"]
    if recommendations.get("max_velocity"):
        lines.append(f"max_velocity: {recommendations['max_velocity']['value']:.0f}")
    if recommendations.get("max_accel"):
        lines.append(f"max_accel: {recommendations['max_accel']['value']:.0f}")
    return "\n".join(lines) + "\n"


def _proposed_slicer(recommendations: Mapping[str, Mapping[str, Any]]) -> str:
    speed = recommendations.get("slicer_motion_speed", {}).get("value")
    return (
        "Operator-applied Shake&Bake slicer motion speed guidance\n"
        "Scope: motion quality only; excludes filament, nozzle, cooling, pressure advance, extrusion flow, and material-specific limits.\n"
        f"speed: {speed:.0f}\n"
        if _finite(speed)
        else "Operator-applied Shake&Bake slicer motion speed guidance unavailable\n"
    )


def _derive_sample_rate(measurement: MeasurementBlock) -> Optional[float]:
    if len(measurement.samples) < 2:
        return None
    duration = measurement.samples[-1].time - measurement.samples[0].time
    if duration <= 0:
        return None
    return (len(measurement.samples) - 1) / duration


def _median_spacing(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    spacings = sorted(b - a for a, b in zip(values, values[1:]))
    return spacings[len(spacings) // 2]


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


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


def _diagnostic(code: str, message: str, subject: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    data = {"code": code, "message": message}
    if subject is not None:
        data["subject"] = subject
    data.update(extra)
    return data


def _warning(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    data = {"code": code, "message": message}
    data.update(extra)
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
