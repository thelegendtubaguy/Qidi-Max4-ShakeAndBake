from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from shakeandbake_capture import Sample

from .config import Max4ConfigSummary
from .preflight import BLOCKING, AdapterSnapshot, Finding, MotionEnvelope, PreflightRequest, run_preflight

STATUS_VALID = "valid"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_INSUFFICIENT_SIGNAL = "insufficient_signal"
STATUS_NOISY = "noisy"
STATUS_MISMATCH = "mismatch"
STATUS_UNAVAILABLE = "unavailable"

CHANNELS = ("accel_x", "accel_y", "accel_z")
SUPPORTED_ORIENTATION_AXES = ("x", "y")


@dataclass(frozen=True)
class OrientationValidationRequest:
    axes: Tuple[str, ...] = SUPPORTED_ORIENTATION_AXES
    move_distance_mm: float = 5.0
    min_signal: float = 0.05
    min_dominance_ratio: float = 1.5
    max_noise_metric: float = 0.35
    safety_margin_mm: float = 5.0

    def normalized_axes(self) -> Tuple[str, ...]:
        return tuple(axis.lower() for axis in self.axes)


@dataclass(frozen=True)
class OrientationMovePlan:
    axis: str
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]


@dataclass(frozen=True)
class OrientationDiagnostic:
    code: str
    message: str
    axis: Optional[str] = None
    severity: str = "warning"


@dataclass(frozen=True)
class OrientationAxisResult:
    axis: str
    status: str
    dominant_channel: Optional[str] = None
    polarity_hint: Optional[str] = None
    dominance_ratio: Optional[float] = None
    noise_metric: Optional[float] = None
    sample_rate_hz: Optional[float] = None
    diagnostics: Tuple[OrientationDiagnostic, ...] = ()


@dataclass(frozen=True)
class OrientationValidationSummary:
    configured_axes_map: Optional[str]
    results: Mapping[str, OrientationAxisResult] = field(default_factory=dict)
    diagnostics: Tuple[OrientationDiagnostic, ...] = ()

    @property
    def status(self) -> str:
        if any(diagnostic.severity == BLOCKING for diagnostic in self.diagnostics):
            return STATUS_UNAVAILABLE
        statuses = {result.status for result in self.results.values()}
        if STATUS_MISMATCH in statuses:
            return STATUS_MISMATCH
        if STATUS_NOISY in statuses:
            return STATUS_NOISY
        if STATUS_AMBIGUOUS in statuses:
            return STATUS_AMBIGUOUS
        if STATUS_INSUFFICIENT_SIGNAL in statuses:
            return STATUS_INSUFFICIENT_SIGNAL
        if statuses and statuses <= {STATUS_VALID}:
            return STATUS_VALID
        return STATUS_UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "configured_axes_map": self.configured_axes_map,
            "results": {axis: _axis_result_to_dict(result) for axis, result in self.results.items()},
            "diagnostics": [_diagnostic_to_dict(diagnostic) for diagnostic in self.diagnostics],
        }


class OrientationValidationAdapter(Protocol):
    def snapshot(self) -> AdapterSnapshot:
        ...

    def acquire_orientation_samples(self, plan: OrientationMovePlan) -> Sequence[Sample]:
        ...


def plan_orientation_moves(config: Max4ConfigSummary, request: OrientationValidationRequest) -> Tuple[OrientationMovePlan, ...]:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    plans = []
    for axis in request.normalized_axes():
        if axis == "z":
            raise ValueError("Max 4 Z movement is unsupported for toolhead accelerometer orientation validation")
        if axis not in SUPPORTED_ORIENTATION_AXES:
            raise ValueError(f"unsupported orientation validation axis: {axis}")
        dx = request.move_distance_mm if axis == "x" else 0.0
        dy = request.move_distance_mm if axis == "y" else 0.0
        plans.append(
            OrientationMovePlan(
                axis=axis,
                start=(float(point[0]), float(point[1]), float(point[2])),
                end=(float(point[0]) + dx, float(point[1]) + dy, float(point[2])),
            )
        )
    return tuple(plans)


def validate_lis2dw_orientation(
    request: OrientationValidationRequest,
    config: Max4ConfigSummary,
    adapter: OrientationValidationAdapter,
) -> OrientationValidationSummary:
    diagnostics: List[OrientationDiagnostic] = []
    axes = request.normalized_axes()
    if any(axis == "z" for axis in axes):
        return OrientationValidationSummary(
            configured_axes_map=config.axes_map,
            diagnostics=(
                OrientationDiagnostic(
                    "z_axis_unsupported",
                    "Max 4 Z movement is unsupported for toolhead accelerometer orientation validation",
                    "z",
                    BLOCKING,
                ),
            ),
        )

    envelope = _orientation_envelope(config, request)
    preflight = run_preflight(PreflightRequest(axes=axes, motion_envelope=envelope, safety_margin_mm=request.safety_margin_mm), config, adapter)
    if preflight.blocking_findings:
        return OrientationValidationSummary(
            configured_axes_map=config.axes_map,
            diagnostics=tuple(
                OrientationDiagnostic(finding.code, finding.message, severity=finding.severity) for finding in preflight.blocking_findings
            ),
        )

    results: Dict[str, OrientationAxisResult] = {}
    plans = plan_orientation_moves(config, request)
    with _orientation_state_context(adapter):
        for plan in plans:
            try:
                samples = list(adapter.acquire_orientation_samples(plan))
            except Exception as exc:
                results[plan.axis] = OrientationAxisResult(
                    axis=plan.axis,
                    status=STATUS_UNAVAILABLE,
                    diagnostics=(OrientationDiagnostic("sample_acquisition_failed", str(exc), plan.axis, BLOCKING),),
                )
                continue
            results[plan.axis] = analyze_orientation_samples(plan.axis, samples, config.axes_map, request)
    return OrientationValidationSummary(configured_axes_map=config.axes_map, results=results, diagnostics=tuple(diagnostics))


def analyze_orientation_samples(
    axis: str,
    samples: Sequence[Sample],
    axes_map: Optional[str],
    request: OrientationValidationRequest | None = None,
) -> OrientationAxisResult:
    request = request or OrientationValidationRequest()
    diagnostics: List[OrientationDiagnostic] = []
    if len(samples) < 2:
        diagnostic = OrientationDiagnostic("insufficient_samples", "orientation validation requires at least two samples", axis)
        return OrientationAxisResult(axis, STATUS_INSUFFICIENT_SIGNAL, diagnostics=(diagnostic,))

    sample_rate = _sample_rate(samples)
    raw_channels = _raw_channels(samples)
    centered = _center_channels_from_raw(raw_channels)
    energies = {channel: sum(value * value for value in values) for channel, values in centered.items()}
    sorted_channels = sorted(energies.items(), key=lambda item: item[1], reverse=True)
    dominant_channel, dominant_energy = sorted_channels[0]
    second_energy = sorted_channels[1][1] if len(sorted_channels) > 1 else 0.0
    amplitude = max(abs(value) for value in centered[dominant_channel])
    dominance_ratio = dominant_energy / max(second_energy, 1e-12)
    noise_metric = _noise_metric(centered[dominant_channel])
    polarity_hint = _polarity_hint(centered[dominant_channel], raw_channels[dominant_channel])

    status = STATUS_VALID
    if amplitude < request.min_signal:
        status = STATUS_INSUFFICIENT_SIGNAL
        diagnostics.append(OrientationDiagnostic("insufficient_signal", "dominant response is below signal threshold", axis))
    elif noise_metric > request.max_noise_metric:
        status = STATUS_NOISY
        diagnostics.append(OrientationDiagnostic("noisy", "orientation validation signal is noisy", axis))
    elif dominance_ratio < request.min_dominance_ratio:
        status = STATUS_AMBIGUOUS
        diagnostics.append(OrientationDiagnostic("ambiguous", "two or more accelerometer channels have similar response dominance", axis))

    expected = _expected_channel(axis, axes_map)
    if expected is not None and status == STATUS_VALID:
        expected_channel, expected_polarity = expected
        if dominant_channel != expected_channel or (expected_polarity and polarity_hint != expected_polarity):
            status = STATUS_MISMATCH
            diagnostics.append(
                OrientationDiagnostic(
                    "axes_map_mismatch",
                    f"observed {dominant_channel}/{polarity_hint} does not match configured axes_map expectation {expected_channel}/{expected_polarity}",
                    axis,
                )
            )

    return OrientationAxisResult(
        axis=axis,
        status=status,
        dominant_channel=dominant_channel,
        polarity_hint=polarity_hint,
        dominance_ratio=dominance_ratio,
        noise_metric=noise_metric,
        sample_rate_hz=sample_rate,
        diagnostics=tuple(diagnostics),
    )


def _orientation_envelope(config: Max4ConfigSummary, request: OrientationValidationRequest) -> MotionEnvelope:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    distance = request.move_distance_mm
    return MotionEnvelope(
        min_x=float(point[0]) - request.safety_margin_mm,
        max_x=float(point[0]) + distance + request.safety_margin_mm,
        min_y=float(point[1]) - request.safety_margin_mm,
        max_y=float(point[1]) + distance + request.safety_margin_mm,
    )


def _sample_rate(samples: Sequence[Sample]) -> Optional[float]:
    duration = samples[-1].time - samples[0].time
    if duration <= 0:
        return None
    return (len(samples) - 1) / duration


def _raw_channels(samples: Sequence[Sample]) -> Dict[str, List[float]]:
    return {
        "accel_x": [sample.accel_x for sample in samples],
        "accel_y": [sample.accel_y for sample in samples],
        "accel_z": [sample.accel_z for sample in samples],
    }


def _center_channels_from_raw(raw: Mapping[str, Sequence[float]]) -> Dict[str, List[float]]:
    return {channel: [value - median(values) for value in values] for channel, values in raw.items()}


def _noise_metric(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    diffs = [abs(current - previous) for previous, current in zip(values, values[1:])]
    amplitude = max(abs(value) for value in values) or 1e-12
    return median(diffs) / amplitude


def _polarity_hint(centered_values: Sequence[float], raw_values: Sequence[float]) -> str:
    baseline = median(raw_values)
    peak_index = max(range(len(centered_values)), key=lambda index: abs(centered_values[index]))
    return "positive" if raw_values[peak_index] >= baseline else "negative"


def _expected_channel(axis: str, axes_map: Optional[str]) -> Optional[Tuple[str, str]]:
    if not axes_map:
        return None
    parts = [part.strip().lower() for part in axes_map.split(",")]
    index = {"x": 0, "y": 1}.get(axis)
    if index is None or index >= len(parts):
        return None
    token = parts[index]
    polarity = "negative" if token.startswith("-") else "positive"
    channel_axis = token[1:] if token.startswith("-") else token
    if channel_axis not in ("x", "y", "z"):
        return None
    return f"accel_{channel_axis}", polarity


class _orientation_state_context:
    def __init__(self, adapter: Any):
        self.adapter = adapter
        self.input_snapshot: Mapping[str, Any] = {}
        self.velocity_snapshot: Mapping[str, Any] = {}

    def __enter__(self):
        snap_input = getattr(self.adapter, "snapshot_input_shaper", None)
        snap_velocity = getattr(self.adapter, "snapshot_velocity_limits", None)
        disable = getattr(self.adapter, "disable_input_shaper", None)
        update = getattr(self.adapter, "update_velocity_limits", None)
        self.input_snapshot = dict(snap_input()) if callable(snap_input) else {}
        self.velocity_snapshot = dict(snap_velocity()) if callable(snap_velocity) else {}
        if callable(disable):
            disable()
        if callable(update):
            update({"orientation_validation": True})
        return self

    def __exit__(self, exc_type, exc, tb):
        restore_input = getattr(self.adapter, "restore_input_shaper", None)
        restore_velocity = getattr(self.adapter, "restore_velocity_limits", None)
        if callable(restore_input):
            restore_input(self.input_snapshot)
        if callable(restore_velocity):
            restore_velocity(self.velocity_snapshot)
        return False


def _axis_result_to_dict(result: OrientationAxisResult) -> Dict[str, Any]:
    return {
        "axis": result.axis,
        "status": result.status,
        "dominant_channel": result.dominant_channel,
        "polarity_hint": result.polarity_hint,
        "dominance_ratio": result.dominance_ratio,
        "noise_metric": result.noise_metric,
        "sample_rate_hz": result.sample_rate_hz,
        "diagnostics": [_diagnostic_to_dict(diagnostic) for diagnostic in result.diagnostics],
    }


def _diagnostic_to_dict(diagnostic: OrientationDiagnostic) -> Dict[str, Any]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "axis": diagnostic.axis,
        "severity": diagnostic.severity,
    }
