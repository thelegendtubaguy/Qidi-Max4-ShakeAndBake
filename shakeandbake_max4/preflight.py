from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple

from .config import DEFAULT_MAX4_XY_BOUNDS, DEFAULT_SUPPORTED_AXES, Max4ConfigSummary

BLOCKING = "blocking"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class MotionEnvelope:
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @classmethod
    def around_point(cls, point: Sequence[float], radius: float) -> "MotionEnvelope":
        return cls(
            min_x=float(point[0]) - radius,
            max_x=float(point[0]) + radius,
            min_y=float(point[1]) - radius,
            max_y=float(point[1]) + radius,
        )


@dataclass(frozen=True)
class ResourceThresholds:
    max_load: Optional[float] = None
    min_free_memory_mb: Optional[float] = None
    min_free_disk_mb: Optional[float] = None


@dataclass(frozen=True)
class PreflightRequest:
    axes: Tuple[str, ...] = DEFAULT_SUPPORTED_AXES
    motion_envelope: Optional[MotionEnvelope] = None
    safety_margin_mm: float = 5.0
    resource_thresholds: ResourceThresholds = field(
        default_factory=lambda: ResourceThresholds(max_load=4.0, min_free_memory_mb=256.0, min_free_disk_mb=512.0)
    )

    def normalized_axes(self) -> Tuple[str, ...]:
        return tuple(axis.lower() for axis in self.axes)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    field: Optional[str] = None
    observed: Any = None


@dataclass(frozen=True)
class AdapterSnapshot:
    printer_ready: bool = True
    printing: bool = False
    paused: bool = False
    virtual_sd_active: bool = False
    homing: bool = False
    accelerometer_available: bool = True
    host_load: Optional[float] = None
    free_memory_mb: Optional[float] = None
    free_disk_mb: Optional[float] = None
    fan_state: Mapping[str, Any] = field(default_factory=dict)
    heater_state: Mapping[str, Any] = field(default_factory=dict)
    chamber_state: Mapping[str, Any] = field(default_factory=dict)
    input_shaper_state: Mapping[str, Any] = field(default_factory=dict)
    velocity_limit_state: Mapping[str, Any] = field(default_factory=dict)
    toolhead_position: Optional[Tuple[float, float, float]] = None
    orientation_validation_summary: Mapping[str, Any] = field(default_factory=dict)


class PreflightAdapter(Protocol):
    def snapshot(self) -> AdapterSnapshot:
        ...


@dataclass(frozen=True)
class StateSnapshot:
    fan_state: Mapping[str, Any] = field(default_factory=dict)
    heater_state: Mapping[str, Any] = field(default_factory=dict)
    chamber_state: Mapping[str, Any] = field(default_factory=dict)
    input_shaper_state: Mapping[str, Any] = field(default_factory=dict)
    velocity_limit_state: Mapping[str, Any] = field(default_factory=dict)
    probe_point: Optional[Tuple[float, float, float]] = None
    accelerometer_identity: Optional[str] = None
    axes_map: Optional[str] = None
    toolhead_position: Optional[Tuple[float, float, float]] = None
    host_load: Optional[float] = None
    free_memory_mb: Optional[float] = None
    free_disk_mb: Optional[float] = None
    orientation_validation_summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    supported_axes: Tuple[str, ...]
    findings: Tuple[Finding, ...]
    state: StateSnapshot

    @property
    def blocking_findings(self) -> Tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == BLOCKING)

    @property
    def warnings(self) -> Tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == WARNING)


@dataclass(frozen=True)
class TestPreflightAdapter:
    state: AdapterSnapshot = field(default_factory=AdapterSnapshot)

    def snapshot(self) -> AdapterSnapshot:
        return self.state


def run_preflight(
    request: PreflightRequest,
    config: Max4ConfigSummary,
    adapter: PreflightAdapter,
) -> PreflightResult:
    adapter_state = adapter.snapshot()
    findings = []

    _check_axes(request, findings)
    _check_readiness(adapter_state, findings)
    _check_motion_envelope(request, config, findings)
    _check_resources(request.resource_thresholds, adapter_state, findings)

    state = StateSnapshot(
        fan_state=dict(adapter_state.fan_state),
        heater_state=dict(adapter_state.heater_state),
        chamber_state=dict(adapter_state.chamber_state),
        input_shaper_state=dict(adapter_state.input_shaper_state) or _configured_input_shaper_state(config),
        velocity_limit_state=dict(adapter_state.velocity_limit_state) or _configured_velocity_limit_state(config),
        probe_point=config.resonance_tester.primary_probe_point,
        accelerometer_identity=config.accelerometer_identity,
        axes_map=config.axes_map,
        toolhead_position=adapter_state.toolhead_position,
        host_load=adapter_state.host_load,
        free_memory_mb=adapter_state.free_memory_mb,
        free_disk_mb=adapter_state.free_disk_mb,
        orientation_validation_summary=dict(adapter_state.orientation_validation_summary),
    )

    blocking = tuple(finding for finding in findings if finding.severity == BLOCKING)
    return PreflightResult(
        ready=not blocking,
        supported_axes=DEFAULT_SUPPORTED_AXES,
        findings=tuple(findings),
        state=state,
    )


def _check_axes(request: PreflightRequest, findings: list[Finding]) -> None:
    requested_axes = request.normalized_axes()
    for axis in requested_axes:
        if axis == "z":
            findings.append(
                Finding(
                    code="z_axis_unsupported",
                    severity=BLOCKING,
                    message="Max 4 Z-axis acquisition is unsupported because Z is bed-driven and not measured by the toolhead accelerometer",
                    field="axes",
                    observed=axis,
                )
            )
        elif axis not in DEFAULT_SUPPORTED_AXES:
            findings.append(
                Finding(
                    code="axis_unsupported",
                    severity=BLOCKING,
                    message=f"unsupported acquisition axis: {axis}",
                    field="axes",
                    observed=axis,
                )
            )


def _check_readiness(state: AdapterSnapshot, findings: list[Finding]) -> None:
    checks = (
        (not state.printer_ready, "printer_not_ready", "printer is not ready", "printer_ready", state.printer_ready),
        (state.printing, "printing", "printer is actively printing", "printing", state.printing),
        (state.paused, "paused", "printer is paused", "paused", state.paused),
        (
            state.virtual_sd_active,
            "virtual_sd_active",
            "virtual SD work is active",
            "virtual_sd_active",
            state.virtual_sd_active,
        ),
        (state.homing, "homing", "printer is homing", "homing", state.homing),
        (
            not state.accelerometer_available,
            "accelerometer_unavailable",
            "accelerometer is unavailable",
            "accelerometer_available",
            state.accelerometer_available,
        ),
    )
    for active, code, message, field, observed in checks:
        if active:
            findings.append(Finding(code=code, severity=BLOCKING, message=message, field=field, observed=observed))


def _check_motion_envelope(request: PreflightRequest, config: Max4ConfigSummary, findings: list[Finding]) -> None:
    envelope = request.motion_envelope
    if envelope is None:
        point = config.resonance_tester.primary_probe_point
        if point is None:
            findings.append(
                Finding(
                    code="missing_probe_point",
                    severity=WARNING,
                    message="no resonance probe point is configured for envelope validation",
                    field="resonance_tester.probe_points",
                )
            )
            return
        envelope = MotionEnvelope.around_point(point, radius=0.0)

    min_x, max_x, min_y, max_y = config.xy_bounds or DEFAULT_MAX4_XY_BOUNDS
    margin = request.safety_margin_mm
    out_of_bounds = (
        envelope.min_x - margin < min_x
        or envelope.max_x + margin > max_x
        or envelope.min_y - margin < min_y
        or envelope.max_y + margin > max_y
    )
    if out_of_bounds:
        findings.append(
            Finding(
                code="motion_envelope_out_of_bounds",
                severity=BLOCKING,
                message="planned X/Y acquisition envelope exceeds configured Max 4 bounds or safety margin",
                field="motion_envelope",
                observed={
                    "envelope": envelope,
                    "xy_bounds": config.xy_bounds,
                    "safety_margin_mm": margin,
                },
            )
        )


def _check_resources(thresholds: ResourceThresholds, state: AdapterSnapshot, findings: list[Finding]) -> None:
    if thresholds.max_load is not None:
        if state.host_load is None:
            findings.append(_resource_unavailable("host_load"))
        elif state.host_load > thresholds.max_load:
            findings.append(
                Finding(
                    code="host_load_warning",
                    severity=WARNING,
                    message="host load exceeds warning threshold",
                    field="host_load",
                    observed=state.host_load,
                )
            )
    if thresholds.min_free_memory_mb is not None:
        if state.free_memory_mb is None:
            findings.append(_resource_unavailable("free_memory_mb"))
        elif state.free_memory_mb < thresholds.min_free_memory_mb:
            findings.append(
                Finding(
                    code="free_memory_warning",
                    severity=WARNING,
                    message="free memory is below warning threshold",
                    field="free_memory_mb",
                    observed=state.free_memory_mb,
                )
            )
    if thresholds.min_free_disk_mb is not None:
        if state.free_disk_mb is None:
            findings.append(_resource_unavailable("free_disk_mb"))
        elif state.free_disk_mb < thresholds.min_free_disk_mb:
            findings.append(
                Finding(
                    code="free_disk_warning",
                    severity=WARNING,
                    message="free disk is below warning threshold",
                    field="free_disk_mb",
                    observed=state.free_disk_mb,
                )
            )


def _resource_unavailable(field: str) -> Finding:
    return Finding(
        code=f"{field}_unavailable",
        severity=WARNING,
        message=f"{field} metric is unavailable",
        field=field,
    )


def _configured_input_shaper_state(config: Max4ConfigSummary) -> Mapping[str, Any]:
    state = {}
    for key in ("shaper_type_x", "shaper_freq_x", "shaper_type_y", "shaper_freq_y", "damping_ratio_x", "damping_ratio_y"):
        value = getattr(config.input_shaper, key)
        if value is not None:
            state[key] = value
    return state


def _configured_velocity_limit_state(config: Max4ConfigSummary) -> Mapping[str, Any]:
    state = {}
    for key in ("max_velocity", "max_accel", "max_z_velocity", "max_z_accel", "square_corner_velocity"):
        value = getattr(config.printer, key)
        if value is not None:
            state[key] = value
    return state
