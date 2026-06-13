from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .models import CaptureArtifact, MeasurementBlock, Sample

SPEED_LIMIT_COMMAND = "SHAKEANDBAKE_CAPTURE_SPEED_LIMITS"
SPEED_LIMIT_METADATA_KEY = "speed_limit_evidence"
PHASE_BASELINE = "endstop_baseline"
PHASE_STRESS = "stress_candidates"
PHASE_SHAPER = "shaper"
PHASE_SPEED_PROFILE = "speed_profile"
DEFAULT_PHASES = (PHASE_BASELINE, PHASE_STRESS, PHASE_SHAPER, PHASE_SPEED_PROFILE)
REQUIRED_SPEED_PROFILE_DIRECTIONS = (45.0, 135.0)


@dataclass(frozen=True)
class SpeedLimitPhase:
    name: str
    enabled: bool = True
    status: str = "planned"
    diagnostics: Sequence[Mapping[str, Any]] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": self.status,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


@dataclass(frozen=True)
class TriggerObservation:
    axis: str
    side: str
    commanded_coordinate: float
    observed_coordinate: Optional[float]
    sample_index: int
    scan_speed: float
    timestamp: str
    available: bool = True
    phase: str = PHASE_BASELINE
    candidate_id: Optional[str] = None
    diagnostic: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis.lower(),
            "side": self.side,
            "commanded_coordinate": self.commanded_coordinate,
            "observed_coordinate": self.observed_coordinate,
            "sample_index": self.sample_index,
            "scan_speed": self.scan_speed,
            "timestamp": self.timestamp,
            "available": self.available,
            "phase": self.phase,
            "candidate_id": self.candidate_id,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class TriggerDrift:
    axis: str
    candidate_id: str
    baseline_coordinate: Optional[float]
    observed_coordinate: Optional[float]
    drift_mm: Optional[float]
    threshold_mm: float
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis.lower(),
            "candidate_id": self.candidate_id,
            "baseline_coordinate": self.baseline_coordinate,
            "observed_coordinate": self.observed_coordinate,
            "drift_mm": self.drift_mm,
            "threshold_mm": self.threshold_mm,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class ClosedLoopObservation:
    phase: str
    candidate_id: Optional[str]
    axis: Optional[str]
    object_name: str
    fields: Mapping[str, Any]
    timestamp: str
    available: bool = True
    unsafe: bool = False
    diagnostic: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "candidate_id": self.candidate_id,
            "axis": self.axis.lower() if isinstance(self.axis, str) else self.axis,
            "object_name": self.object_name,
            "fields": dict(self.fields),
            "timestamp": self.timestamp,
            "available": self.available,
            "unsafe": self.unsafe,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class SpeedLimitCandidate:
    candidate_id: str
    velocity: float
    acceleration: float
    directions: Sequence[str]
    repetitions: int
    segment_length: float
    planned_envelope: Mapping[str, float]
    planner_settings: Mapping[str, Any]
    status: str = "planned"
    trigger_drift: Sequence[TriggerDrift] = ()
    safety_stop: Optional[Mapping[str, Any]] = None
    diagnostics: Sequence[Mapping[str, Any]] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "directions": list(self.directions),
            "repetitions": self.repetitions,
            "segment_length": self.segment_length,
            "planned_envelope": dict(self.planned_envelope),
            "planner_settings": dict(self.planner_settings),
            "status": self.status,
            "trigger_drift": [item.to_dict() for item in self.trigger_drift],
            "safety_stop": dict(self.safety_stop) if self.safety_stop else None,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


@dataclass(frozen=True)
class SafetyStop:
    reason: str
    phase: str
    candidate_id: Optional[str] = None
    axis: Optional[str] = None
    observed: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "phase": self.phase,
            "candidate_id": self.candidate_id,
            "axis": self.axis,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class SpeedProfilePlan:
    speeds: Sequence[float]
    directions: Sequence[Mapping[str, Any]]
    acceleration: float
    travel_speed: float
    segment_length: float
    max_measurements: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speeds": list(self.speeds),
            "directions": [dict(item) for item in self.directions],
            "acceleration": self.acceleration,
            "travel_speed": self.travel_speed,
            "segment_length": self.segment_length,
            "max_measurements": self.max_measurements,
        }


@dataclass(frozen=True)
class RecommendationInputs:
    derate: float = 0.85
    max_drift_mm: float = 0.05
    min_preferred_speed_width: float = 20.0
    slicer_speed_scope: str = "motion_quality_only"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "derate": self.derate,
            "max_drift_mm": self.max_drift_mm,
            "min_preferred_speed_width": self.min_preferred_speed_width,
            "slicer_speed_scope": self.slicer_speed_scope,
        }


def speed_limit_metadata(
    *,
    phases: Sequence[SpeedLimitPhase | Mapping[str, Any]],
    candidates: Sequence[SpeedLimitCandidate | Mapping[str, Any]],
    trigger_observations: Sequence[TriggerObservation | Mapping[str, Any]],
    closed_loop_observations: Sequence[ClosedLoopObservation | Mapping[str, Any]] = (),
    safety_stops: Sequence[SafetyStop | Mapping[str, Any]] = (),
    speed_profile_plan: Optional[SpeedProfilePlan | Mapping[str, Any]] = None,
    recommendation_inputs: Optional[RecommendationInputs | Mapping[str, Any]] = None,
    diagnostics: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    return {
        "phases": [_as_dict(item) for item in phases],
        "candidates": [_as_dict(item) for item in candidates],
        "trigger_observations": [_as_dict(item) for item in trigger_observations],
        "closed_loop_observations": [_as_dict(item) for item in closed_loop_observations],
        "safety_stops": [_as_dict(item) for item in safety_stops],
        "speed_profile_plan": _as_dict(speed_profile_plan) if speed_profile_plan is not None else None,
        "recommendation_inputs": _as_dict(recommendation_inputs or RecommendationInputs()),
        "diagnostics": [dict(item) for item in diagnostics],
    }


def make_valid_speed_limit_capture(
    *,
    created_at: str = "2026-01-01T00:00:00+00:00",
    include_shaper: bool = True,
    include_speed_profile: bool = True,
) -> CaptureArtifact:
    samples = synthetic_samples()
    measurements: List[MeasurementBlock] = []
    if include_shaper:
        measurements.extend(
            [
                MeasurementBlock("x_shaper", "x", "lis2dw", samples, metadata={"direction_vector": [1, 0, 0]}),
                MeasurementBlock("y_shaper", "y", "lis2dw", samples, metadata={"direction_vector": [0, 1, 0]}),
            ]
        )
    speeds = (100.0, 200.0, 300.0)
    directions = speed_profile_directions()
    if include_speed_profile:
        for speed in speeds:
            for direction in directions:
                angle = direction["angle_degrees"]
                measurements.append(
                    MeasurementBlock(
                        name=f"speed_profile_{int(angle)}_{int(speed)}",
                        axis="speed_profile",
                        sensor="lis2dw",
                        samples=samples,
                        metadata={
                            "kind": "speed_profile",
                            "speed": speed,
                            "direction_angle": angle,
                            "direction_vector": direction["unit_vector"],
                            "segment_length": 60.0,
                            "acceleration": 10000.0,
                            "travel_speed": speed,
                            "accelerometer_object": "lis2dw",
                        },
                    )
                )
    observations = []
    for axis, coordinate in (("x", 392.0), ("y", -1.0)):
        for index in range(3):
            observations.append(
                TriggerObservation(axis, "max" if axis == "x" else "min", coordinate, coordinate + index * 0.001, index, 20.0, created_at)
            )
    candidate = SpeedLimitCandidate(
        "v200-a10000-001",
        200.0,
        10000.0,
        ("x", "y", "diag_45", "diag_135"),
        2,
        80.0,
        {"min_x": 115.0, "max_x": 275.0, "min_y": 115.0, "max_y": 275.0},
        {"max_velocity": 800.0, "max_accel": 30000.0, "square_corner_velocity": 8.0},
        status="passed",
        trigger_drift=(
            TriggerDrift("x", "v200-a10000-001", 392.001, 392.002, 0.001, 0.05, True),
            TriggerDrift("y", "v200-a10000-001", -0.999, -1.000, 0.001, 0.05, True),
        ),
    )
    metadata = _base_metadata()
    metadata[SPEED_LIMIT_METADATA_KEY] = speed_limit_metadata(
        phases=[SpeedLimitPhase(name, status="complete") for name in DEFAULT_PHASES],
        candidates=[candidate],
        trigger_observations=observations,
        closed_loop_observations=[ClosedLoopObservation(PHASE_BASELINE, None, "x", "closed_loop x", {"status": "ok"}, created_at)],
        speed_profile_plan=SpeedProfilePlan(speeds, directions, 10000.0, 200.0, 60.0, 64),
    )
    return CaptureArtifact(
        created_at=created_at,
        command=SPEED_LIMIT_COMMAND,
        parameters={"max_speed": 300.0, "speed_increment": 100.0, "max_drift": 0.05},
        measurements=measurements,
        metadata=metadata,
    )


def make_invalid_speed_limit_capture(kind: str) -> CaptureArtifact:
    capture = make_valid_speed_limit_capture()
    evidence = dict(capture.metadata[SPEED_LIMIT_METADATA_KEY])
    if kind == "missing_baseline":
        evidence["trigger_observations"] = []
    elif kind == "malformed_candidate":
        evidence["candidates"] = [{"candidate_id": "broken"}]
    elif kind == "unavailable_trigger":
        observations = list(evidence["trigger_observations"])
        observations[0] = {**observations[0], "available": False, "observed_coordinate": None, "diagnostic": "unavailable"}
        evidence["trigger_observations"] = observations
    elif kind == "closed_loop_fault":
        evidence["closed_loop_observations"] = [
            ClosedLoopObservation(PHASE_STRESS, "v200-a10000-001", "x", "closed_loop x", {"fault": True}, capture.created_at, unsafe=True).to_dict()
        ]
    elif kind == "incomplete_vibration":
        capture.measurements[:] = [m for m in capture.measurements if m.metadata.get("direction_angle") != 135.0]
    else:
        evidence["diagnostics"] = [{"code": "invalid_fixture_kind", "message": kind}]
    capture.metadata[SPEED_LIMIT_METADATA_KEY] = evidence
    return capture


def speed_profile_directions() -> List[Dict[str, Any]]:
    return [
        {"label": "diag_45", "angle_degrees": 45.0, "unit_vector": [1, 1, 0]},
        {"label": "diag_135", "angle_degrees": 135.0, "unit_vector": [-1, 1, 0]},
    ]


def synthetic_samples(count: int = 128, sample_rate_hz: float = 1000.0, frequency_hz: float = 40.0) -> List[Sample]:
    import math

    return [
        Sample(
            time=index / sample_rate_hz,
            accel_x=math.sin(2.0 * math.pi * frequency_hz * index / sample_rate_hz),
            accel_y=0.5 * math.sin(2.0 * math.pi * (frequency_hz + 5.0) * index / sample_rate_hz),
            accel_z=9.8 + 0.2 * math.sin(2.0 * math.pi * (frequency_hz + 11.0) * index / sample_rate_hz),
        )
        for index in range(count)
    ]


def _base_metadata() -> Dict[str, Any]:
    return {
        "planned_motion_envelope": {"min_x": 115.0, "max_x": 275.0, "min_y": 115.0, "max_y": 275.0},
        "probe_point": [195.0, 195.0, 10.0],
        "axes_map": "y, z, -x",
        "input_shaper_state": {"enabled": True},
        "velocity_limit_state": {"max_velocity": 800.0, "max_accel": 30000.0, "square_corner_velocity": 8.0},
        "fan_heater_chamber_state": {"fans": {}, "heaters": {}, "chamber": {}},
        "accelerometer_identity": "lis2dw",
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    return dict(value)
