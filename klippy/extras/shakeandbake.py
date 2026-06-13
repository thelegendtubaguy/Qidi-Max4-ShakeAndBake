from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import CaptureArtifact, MeasurementBlock, Sample, write_capture_artifact
from shakeandbake_max4 import AdapterSnapshot, MotionEnvelope, PreflightRequest, ResourceThresholds, run_preflight
from shakeandbake_max4.config import DEFAULT_MAX4_XY_BOUNDS, Max4ConfigSummary, parse_max4_config

SUPPORTED_SHAPER_AXES = ("x", "y")
BELT_PATH_DIRECTIONS = {
    "A": (1, -1, 0),
    "B": (1, 1, 0),
}
COMMAND_HELP = {
    "SHAKEANDBAKE_PREFLIGHT": "Report Shake&Bake Max 4 preflight readiness and metadata.",
    "SHAKEANDBAKE_CAPTURE_SHAPER": "Capture raw X/Y shaper accelerometer data for external analysis.",
    "SHAKEANDBAKE_CAPTURE_BELTS": "Capture raw CoreXY A/B belt-path accelerometer data for external analysis.",
}
DEFAULT_OUTPUT_DIR = "shakeandbake-captures"


class CommandError(Exception):
    pass


@dataclass(frozen=True)
class ShaperCaptureParams:
    axes: Tuple[str, ...]
    freq_start: float
    freq_end: float
    hz_per_sec: float
    accel_per_hz: float
    travel_speed: float
    accel_chip: Optional[str]
    output_dir: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "axis": "all" if self.axes == SUPPORTED_SHAPER_AXES else self.axes[0],
            "axes": list(self.axes),
            "freq_start": self.freq_start,
            "freq_end": self.freq_end,
            "hz_per_sec": self.hz_per_sec,
            "accel_per_hz": self.accel_per_hz,
            "travel_speed": self.travel_speed,
            "accel_chip": self.accel_chip,
            "output_dir": self.output_dir,
        }


@dataclass(frozen=True)
class BeltCaptureParams:
    freq_start: float
    freq_end: float
    hz_per_sec: float
    accel_per_hz: float
    travel_speed: float
    accel_chip: Optional[str]
    output_dir: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "paths": list(BELT_PATH_DIRECTIONS),
            "freq_start": self.freq_start,
            "freq_end": self.freq_end,
            "hz_per_sec": self.hz_per_sec,
            "accel_per_hz": self.accel_per_hz,
            "travel_speed": self.travel_speed,
            "accel_chip": self.accel_chip,
            "output_dir": self.output_dir,
        }


@dataclass(frozen=True)
class RestorationStatus:
    input_shaper_restored: bool = True
    velocity_limits_restored: bool = True
    errors: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.input_shaper_restored and self.velocity_limits_restored and not self.errors


class KlipperAdapter:
    def __init__(self, config: Any):
        self.config = config
        self.printer = config.get_printer() if hasattr(config, "get_printer") else getattr(config, "printer", None)
        self.gcode = self.lookup_object("gcode", required=False)
        self.toolhead = self.lookup_object("toolhead", required=False)
        self.input_shaper = self.lookup_object("input_shaper", required=False)
        self.resonance_tester = self.lookup_object("resonance_tester", required=False)
        self.virtual_sd = self.lookup_object("virtual_sdcard", required=False)
        self.pause_resume = self.lookup_object("pause_resume", required=False)
        self.accelerometer = None

    def register_commands(self, owner: "ShakeAndBake") -> None:
        if self.gcode is None or not hasattr(self.gcode, "register_command"):
            raise CommandError("required Klipper gcode object is unavailable")
        self._register_command("SHAKEANDBAKE_PREFLIGHT", owner.cmd_preflight)
        self._register_command("SHAKEANDBAKE_CAPTURE_SHAPER", owner.cmd_capture_shaper)
        self._register_command("SHAKEANDBAKE_CAPTURE_BELTS", owner.cmd_capture_belts)

    def _register_command(self, name: str, callback: Any) -> None:
        try:
            self.gcode.register_command(name, callback, desc=COMMAND_HELP[name])
        except TypeError:
            self.gcode.register_command(name, callback)

    def lookup_object(self, name: str, required: bool = True) -> Any:
        if self.printer is None:
            if required:
                raise CommandError("required Klipper printer object is unavailable")
            return None
        lookup = getattr(self.printer, "lookup_object", None)
        if not callable(lookup):
            if required:
                raise CommandError("required Klipper object lookup is unavailable")
            return None
        try:
            return lookup(name)
        except TypeError:
            return lookup(name, None)
        except Exception as exc:
            if required:
                raise CommandError(f"required Klipper object '{name}' is unavailable: {exc}")
            return None

    def feature_errors(self) -> List[str]:
        errors = []
        if self.gcode is None or not hasattr(self.gcode, "register_command"):
            errors.append("gcode command registration is unavailable")
        if self.toolhead is None:
            errors.append("toolhead object is unavailable")
        if self.resonance_tester is None:
            errors.append("resonance_tester object is unavailable")
        if not self.accelerometer_available():
            errors.append("accelerometer object or sample acquisition method is unavailable")
        return errors

    def snapshot(self) -> AdapterSnapshot:
        return AdapterSnapshot(
            printer_ready=self.printer_ready(),
            printing=self.is_printing(),
            paused=self.is_paused(),
            virtual_sd_active=self.virtual_sd_active(),
            homing=self.is_homing(),
            accelerometer_available=self.accelerometer_available(),
            host_load=self._optional_float_from(self.printer, "host_load"),
            free_memory_mb=self._optional_float_from(self.printer, "free_memory_mb"),
            free_disk_mb=self._optional_float_from(self.printer, "free_disk_mb"),
            fan_state=self._state_from("fan_state"),
            heater_state=self._state_from("heater_state"),
            chamber_state=self._state_from("chamber_state"),
            input_shaper_state=self.snapshot_input_shaper(),
            velocity_limit_state=self.snapshot_velocity_limits(),
            toolhead_position=self._toolhead_position(),
            orientation_validation_summary=self._orientation_validation_summary(),
        )

    def printer_ready(self) -> bool:
        return bool(_call_or_attr(self.printer, "is_ready", default=True))

    def is_printing(self) -> bool:
        return bool(
            _call_or_attr(self.printer, "printing", default=False)
            or _call_or_attr(self.virtual_sd, "is_active", default=False)
            and bool(_call_or_attr(self.virtual_sd, "printing", default=True))
        )

    def is_paused(self) -> bool:
        return bool(_call_or_attr(self.pause_resume, "is_paused", default=False) or _call_or_attr(self.printer, "paused", default=False))

    def virtual_sd_active(self) -> bool:
        return bool(_call_or_attr(self.virtual_sd, "is_active", default=False) or _call_or_attr(self.printer, "virtual_sd_active", default=False))

    def is_homing(self) -> bool:
        return bool(_call_or_attr(self.toolhead, "is_homing", default=False) or _call_or_attr(self.printer, "homing", default=False))

    def accelerometer_available(self) -> bool:
        return self._accelerometer() is not None

    def snapshot_input_shaper(self) -> Mapping[str, Any]:
        obj = self.input_shaper
        if obj is None:
            return {}
        snapshot = getattr(obj, "snapshot", None)
        if callable(snapshot):
            return dict(snapshot())
        state = getattr(obj, "state", None)
        if isinstance(state, Mapping):
            return dict(state)
        return {key: value for key, value in getattr(obj, "__dict__", {}).items() if _public_data(key, value)}

    def disable_input_shaper(self) -> None:
        obj = self.input_shaper
        if obj is None:
            return
        disable = getattr(obj, "disable", None) or getattr(obj, "disable_shaping", None)
        if callable(disable):
            disable()
            return
        setattr(obj, "enabled", False)

    def restore_input_shaper(self, snapshot: Mapping[str, Any]) -> None:
        obj = self.input_shaper
        if obj is None:
            return
        restore = getattr(obj, "restore", None)
        if callable(restore):
            restore(dict(snapshot))
            return
        state = getattr(obj, "state", None)
        if isinstance(state, dict):
            state.clear()
            state.update(snapshot)
        else:
            for key, value in snapshot.items():
                setattr(obj, key, value)

    def snapshot_velocity_limits(self) -> Mapping[str, Any]:
        obj = self.toolhead
        if obj is None:
            return {}
        snapshot = getattr(obj, "snapshot_velocity_limits", None)
        if callable(snapshot):
            return dict(snapshot())
        state = getattr(obj, "velocity_limits", None)
        if isinstance(state, Mapping):
            return dict(state)
        keys = ("max_velocity", "max_accel", "square_corner_velocity", "max_z_velocity", "max_z_accel")
        return {key: getattr(obj, key) for key in keys if hasattr(obj, key)}

    def update_velocity_limits(self, params: Any) -> None:
        obj = self.toolhead
        if obj is None:
            return
        travel_speed = getattr(params, "travel_speed", None)
        update = getattr(obj, "update_velocity_limits", None)
        if callable(update):
            update(max_velocity=travel_speed) if travel_speed is not None else update()
            return
        if travel_speed is not None and hasattr(obj, "max_velocity"):
            setattr(obj, "max_velocity", travel_speed)

    def restore_velocity_limits(self, snapshot: Mapping[str, Any]) -> None:
        obj = self.toolhead
        if obj is None:
            return
        restore = getattr(obj, "restore_velocity_limits", None)
        if callable(restore):
            restore(dict(snapshot))
            return
        state = getattr(obj, "velocity_limits", None)
        if isinstance(state, dict):
            state.clear()
            state.update(snapshot)
        else:
            for key, value in snapshot.items():
                setattr(obj, key, value)

    def acquire_axis_samples(self, axis: str, params: ShaperCaptureParams) -> List[Sample]:
        accelerometer = self._accelerometer(params.accel_chip)
        if accelerometer is None:
            raise CommandError("accelerometer is unavailable")
        move = getattr(self.resonance_tester, "run_axis", None)
        if callable(move):
            move(axis=axis, params=params.as_dict())
        acquire = getattr(accelerometer, "acquire_samples", None) or getattr(accelerometer, "read_samples", None)
        if not callable(acquire):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        raw_samples = acquire(axis=axis, params=params.as_dict())
        return [Sample.from_value(row) for row in raw_samples]

    def acquire_belt_path_samples(self, path: str, direction: Tuple[int, int, int], params: BeltCaptureParams) -> List[Sample]:
        accelerometer = self._accelerometer(params.accel_chip)
        if accelerometer is None:
            raise CommandError("accelerometer is unavailable")
        run_path = getattr(self.resonance_tester, "run_belt_path", None)
        if callable(run_path):
            run_path(path=path, direction=direction, params=params.as_dict())
        else:
            run_axis = getattr(self.resonance_tester, "run_axis", None)
            if callable(run_axis):
                run_axis(axis=path.lower(), params={**params.as_dict(), "direction_vector": list(direction)})
        acquire = getattr(accelerometer, "acquire_samples", None) or getattr(accelerometer, "read_samples", None)
        if not callable(acquire):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        raw_samples = acquire(axis=path.lower(), params={**params.as_dict(), "direction_vector": list(direction)})
        return [Sample.from_value(row) for row in raw_samples]

    def respond(self, gcmd: Any, message: str) -> None:
        responder = getattr(gcmd, "respond_info", None) if gcmd is not None else None
        if callable(responder):
            responder(message)
            return
        if self.gcode is not None and callable(getattr(self.gcode, "respond_info", None)):
            self.gcode.respond_info(message)

    def _accelerometer(self, name: Optional[str] = None) -> Any:
        if self.accelerometer is not None:
            return self.accelerometer
        candidates = [name, "lis2dw", "adxl345"]
        for candidate in candidates:
            if not candidate:
                continue
            obj = self.lookup_object(candidate, required=False)
            if obj is not None:
                self.accelerometer = obj
                return obj
        obj = getattr(self.printer, "accelerometer", None)
        if obj is not None:
            self.accelerometer = obj
        return obj

    def _state_from(self, attr: str) -> Mapping[str, Any]:
        value = _call_or_attr(self.printer, attr, default={})
        return dict(value) if isinstance(value, Mapping) else {}

    def _optional_float_from(self, obj: Any, attr: str) -> Optional[float]:
        value = _call_or_attr(obj, attr, default=None)
        return None if value is None else float(value)

    def _toolhead_position(self) -> Optional[Tuple[float, float, float]]:
        value = _call_or_attr(self.toolhead, "get_position", default=None) or _call_or_attr(self.toolhead, "position", default=None)
        if value is None:
            return None
        return tuple(float(item) for item in value[:3])  # type: ignore[index]

    def _orientation_validation_summary(self) -> Mapping[str, Any]:
        value = _call_or_attr(self.printer, "orientation_validation_summary", default={})
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return dict(value) if isinstance(value, Mapping) else {}


class AcquisitionContext:
    def __init__(self, adapter: KlipperAdapter, params: Any):
        self.adapter = adapter
        self.params = params
        self.input_shaper_snapshot: Mapping[str, Any] = {}
        self.velocity_limit_snapshot: Mapping[str, Any] = {}
        self.restoration_status = RestorationStatus()

    def __enter__(self) -> "AcquisitionContext":
        self.input_shaper_snapshot = self.adapter.snapshot_input_shaper()
        self.velocity_limit_snapshot = self.adapter.snapshot_velocity_limits()
        self.adapter.disable_input_shaper()
        self.adapter.update_velocity_limits(self.params)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        errors = []
        input_ok = True
        velocity_ok = True
        try:
            self.adapter.restore_input_shaper(self.input_shaper_snapshot)
        except Exception as restore_exc:  # pragma: no cover - asserted through status in tests
            input_ok = False
            errors.append(f"input_shaper_restore_failed: {restore_exc}")
        try:
            self.adapter.restore_velocity_limits(self.velocity_limit_snapshot)
        except Exception as restore_exc:  # pragma: no cover - asserted through status in tests
            velocity_ok = False
            errors.append(f"velocity_limits_restore_failed: {restore_exc}")
        self.restoration_status = RestorationStatus(input_ok, velocity_ok, tuple(errors))
        return False


class ShakeAndBake:
    def __init__(self, config: Any):
        self.config = config
        self.adapter = KlipperAdapter(config)
        self.max4_config = _build_max4_config(config)
        self.adapter.register_commands(self)

    def cmd_preflight(self, gcmd: Any) -> None:
        result = run_preflight(PreflightRequest(), self.max4_config, self.adapter)
        self.adapter.respond(gcmd, _format_preflight_result(result))

    def cmd_capture_shaper(self, gcmd: Any) -> None:
        params = _parse_capture_params(gcmd, self.max4_config)
        if any(axis not in SUPPORTED_SHAPER_AXES for axis in params.axes):
            raise CommandError("Max 4 Shake&Bake shaper acquisition supports X and Y only")

        preflight_request = PreflightRequest(axes=params.axes, motion_envelope=_planned_envelope(self.max4_config), safety_margin_mm=5.0)
        preflight_result = run_preflight(preflight_request, self.max4_config, self.adapter)
        if preflight_result.blocking_findings:
            codes = ", ".join(finding.code for finding in preflight_result.blocking_findings)
            raise CommandError(f"Shake&Bake preflight failed: {codes}")

        feature_errors = self.adapter.feature_errors()
        if feature_errors:
            raise CommandError("Shake&Bake feature detection failed: " + "; ".join(feature_errors))

        measurements: List[MeasurementBlock] = []
        restoration_status = RestorationStatus()
        try:
            with AcquisitionContext(self.adapter, params) as context:
                for axis in params.axes:
                    samples = self.adapter.acquire_axis_samples(axis, params)
                    measurements.append(_measurement_for_axis(axis, samples, params, self.max4_config))
            restoration_status = context.restoration_status
        except Exception:
            restoration_status = getattr(locals().get("context", None), "restoration_status", restoration_status)
            raise
        finally:
            if not restoration_status.ok:
                self.adapter.respond(gcmd, "Shake&Bake restoration warnings: " + "; ".join(restoration_status.errors))

        artifact = _capture_artifact(params, measurements, self.max4_config, preflight_result, restoration_status)
        output_path = _output_path(params)
        write_result = write_capture_artifact(output_path, artifact)
        if not write_result.ok:
            codes = ", ".join(d.status_code for d in write_result.validation.diagnostics)
            raise CommandError(f"capture artifact validation failed: {codes}")
        self.adapter.respond(
            gcmd,
            "Shake&Bake capture complete: "
            f"path={write_result.path} measurements={','.join(measurement.name for measurement in measurements)}",
        )

    def cmd_capture_belts(self, gcmd: Any) -> None:
        params = _parse_belt_params(gcmd, self.max4_config)
        preflight_request = PreflightRequest(axes=SUPPORTED_SHAPER_AXES, motion_envelope=_belt_planned_envelope(self.max4_config), safety_margin_mm=5.0)
        preflight_result = run_preflight(preflight_request, self.max4_config, self.adapter)
        if preflight_result.blocking_findings:
            codes = ", ".join(finding.code for finding in preflight_result.blocking_findings)
            raise CommandError(f"Shake&Bake belt preflight failed: {codes}")

        feature_errors = self.adapter.feature_errors()
        if feature_errors:
            raise CommandError("Shake&Bake feature detection failed: " + "; ".join(feature_errors))

        measurements: List[MeasurementBlock] = []
        restoration_status = RestorationStatus()
        try:
            with AcquisitionContext(self.adapter, params) as context:
                for path, direction in BELT_PATH_DIRECTIONS.items():
                    samples = self.adapter.acquire_belt_path_samples(path, direction, params)
                    measurements.append(_measurement_for_belt_path(path, direction, samples, params, self.max4_config))
            restoration_status = context.restoration_status
        except Exception:
            restoration_status = getattr(locals().get("context", None), "restoration_status", restoration_status)
            raise
        finally:
            if not restoration_status.ok:
                self.adapter.respond(gcmd, "Shake&Bake restoration warnings: " + "; ".join(restoration_status.errors))

        artifact = _belt_capture_artifact(params, measurements, self.max4_config, preflight_result, restoration_status)
        output_path = _belt_output_path(params)
        write_result = write_capture_artifact(output_path, artifact)
        if not write_result.ok:
            codes = ", ".join(d.status_code for d in write_result.validation.diagnostics)
            raise CommandError(f"belt capture artifact validation failed: {codes}")
        self.adapter.respond(
            gcmd,
            "Shake&Bake belt capture complete: "
            f"path={write_result.path} measurements={','.join(measurement.name for measurement in measurements)}",
        )


def load_config(config: Any) -> ShakeAndBake:
    return ShakeAndBake(config)


def _build_max4_config(config: Any) -> Max4ConfigSummary:
    value = getattr(config, "max4_config", None)
    if isinstance(value, Max4ConfigSummary):
        return value
    config_text = getattr(config, "config_text", None)
    if config_text:
        return parse_max4_config(config_text)
    config_path = getattr(config, "config_path", None)
    if config_path:
        return parse_max4_config(Path(config_path))
    return Max4ConfigSummary()


def _parse_capture_params(gcmd: Any, config: Max4ConfigSummary) -> ShaperCaptureParams:
    axis_raw = _gcmd_get(gcmd, "AXIS", "ALL").lower()
    if axis_raw == "all":
        axes = SUPPORTED_SHAPER_AXES
    elif axis_raw in SUPPORTED_SHAPER_AXES:
        axes = (axis_raw,)
    else:
        raise CommandError("Max 4 Shake&Bake shaper acquisition supports AXIS=X, AXIS=Y, or AXIS=ALL")

    freq_start = _gcmd_float(gcmd, "FREQ_START", 5.0, above=0.0)
    freq_end = _gcmd_float(gcmd, "FREQ_END", 120.0, above=freq_start)
    hz_per_sec = _gcmd_float(gcmd, "HZ_PER_SEC", 1.0, above=0.0)
    accel_per_hz = _gcmd_float(gcmd, "ACCEL_PER_HZ", config.resonance_tester.accel_per_hz or 75.0, above=0.0)
    travel_speed = _gcmd_float(gcmd, "TRAVEL_SPEED", config.printer.max_velocity or 100.0, above=0.0)
    accel_chip = _gcmd_get(gcmd, "ACCEL_CHIP", config.accelerometer_identity)
    output_dir = _gcmd_get(gcmd, "OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    return ShaperCaptureParams(axes, freq_start, freq_end, hz_per_sec, accel_per_hz, travel_speed, accel_chip, output_dir)


def _parse_belt_params(gcmd: Any, config: Max4ConfigSummary) -> BeltCaptureParams:
    kinematics = (config.printer.kinematics or "").lower()
    if kinematics and kinematics != "corexy":
        raise CommandError("SHAKEANDBAKE_CAPTURE_BELTS supports QIDI Max 4 CoreXY kinematics only")
    axis_raw = _gcmd_get(gcmd, "AXIS", None)
    if axis_raw is not None:
        raise CommandError("SHAKEANDBAKE_CAPTURE_BELTS captures CoreXY A/B belt paths only; Z-axis and AXIS parameters are unsupported")
    freq_start = _gcmd_float(gcmd, "FREQ_START", 5.0, above=0.0)
    freq_end = _gcmd_float(gcmd, "FREQ_END", 120.0, above=freq_start)
    hz_per_sec = _gcmd_float(gcmd, "HZ_PER_SEC", 1.0, above=0.0)
    accel_per_hz = _gcmd_float(gcmd, "ACCEL_PER_HZ", config.resonance_tester.accel_per_hz or 75.0, above=0.0)
    travel_speed = _gcmd_float(gcmd, "TRAVEL_SPEED", config.printer.max_velocity or 100.0, above=0.0)
    accel_chip = _gcmd_get(gcmd, "ACCEL_CHIP", config.accelerometer_identity)
    output_dir = _gcmd_get(gcmd, "OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    return BeltCaptureParams(freq_start, freq_end, hz_per_sec, accel_per_hz, travel_speed, accel_chip, output_dir)


def _gcmd_get(gcmd: Any, key: str, default: Any) -> Any:
    getter = getattr(gcmd, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(gcmd, key.lower(), default)


def _gcmd_float(gcmd: Any, key: str, default: float, above: Optional[float] = None) -> float:
    getter = getattr(gcmd, "get_float", None)
    if callable(getter):
        return float(getter(key, default, above=above))
    value = float(_gcmd_get(gcmd, key, default))
    if above is not None and value <= above:
        raise CommandError(f"{key} must be greater than {above}")
    return value


def _planned_envelope(config: Max4ConfigSummary) -> MotionEnvelope:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    return MotionEnvelope.around_point(point, radius=10.0)


def _belt_planned_envelope(config: Max4ConfigSummary) -> MotionEnvelope:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    radius = 10.0
    return MotionEnvelope(
        min_x=float(point[0]) - radius,
        max_x=float(point[0]) + radius,
        min_y=float(point[1]) - radius,
        max_y=float(point[1]) + radius,
    )


def _measurement_for_axis(
    axis: str, samples: Sequence[Sample], params: ShaperCaptureParams, config: Max4ConfigSummary
) -> MeasurementBlock:
    return MeasurementBlock(
        name=f"{axis}_shaper",
        axis=axis,
        sensor=params.accel_chip or config.accelerometer_identity,
        sample_rate_hz=None,
        samples=list(samples),
        metadata={
            "direction_vector": [1, 0, 0] if axis == "x" else [0, 1, 0],
            "freq_start": params.freq_start,
            "freq_end": params.freq_end,
            "hz_per_sec": params.hz_per_sec,
            "accel_per_hz": params.accel_per_hz,
            "travel_speed": params.travel_speed,
            "accelerometer_object": params.accel_chip or config.accelerometer_identity,
        },
    )


def _measurement_for_belt_path(
    path: str,
    direction: Tuple[int, int, int],
    samples: Sequence[Sample],
    params: BeltCaptureParams,
    config: Max4ConfigSummary,
) -> MeasurementBlock:
    return MeasurementBlock(
        name=f"belt_{path.lower()}",
        axis=path.lower(),
        sensor=params.accel_chip or config.accelerometer_identity,
        sample_rate_hz=None,
        samples=list(samples),
        metadata={
            "path_label": path,
            "direction_vector": list(direction),
            "freq_start": params.freq_start,
            "freq_end": params.freq_end,
            "hz_per_sec": params.hz_per_sec,
            "accel_per_hz": params.accel_per_hz,
            "travel_speed": params.travel_speed,
            "accelerometer_object": params.accel_chip or config.accelerometer_identity,
        },
    )


def _capture_artifact(
    params: ShaperCaptureParams,
    measurements: Sequence[MeasurementBlock],
    config: Max4ConfigSummary,
    preflight_result: Any,
    restoration_status: RestorationStatus,
) -> CaptureArtifact:
    envelope = _planned_envelope(config)
    state = preflight_result.state
    return CaptureArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        command="SHAKEANDBAKE_CAPTURE_SHAPER",
        parameters=params.as_dict(),
        measurements=list(measurements),
        metadata={
            "planned_motion_envelope": {
                "min_x": envelope.min_x,
                "max_x": envelope.max_x,
                "min_y": envelope.min_y,
                "max_y": envelope.max_y,
            },
            "probe_point": list(state.probe_point) if state.probe_point else None,
            "axes_map": state.axes_map,
            "input_shaper_state": dict(state.input_shaper_state),
            "velocity_limit_state": dict(state.velocity_limit_state),
            "fan_heater_chamber_state": {
                "fans": dict(state.fan_state),
                "heaters": dict(state.heater_state),
                "chamber": dict(state.chamber_state),
            },
            "accelerometer_identity": state.accelerometer_identity,
            "preflight_warnings": [finding.code for finding in preflight_result.warnings],
            "restoration_status": {
                "ok": restoration_status.ok,
                "input_shaper_restored": restoration_status.input_shaper_restored,
                "velocity_limits_restored": restoration_status.velocity_limits_restored,
                "errors": list(restoration_status.errors),
            },
            "orientation_validation_summary": dict(state.orientation_validation_summary),
        },
    )


def _belt_capture_artifact(
    params: BeltCaptureParams,
    measurements: Sequence[MeasurementBlock],
    config: Max4ConfigSummary,
    preflight_result: Any,
    restoration_status: RestorationStatus,
) -> CaptureArtifact:
    envelope = _belt_planned_envelope(config)
    state = preflight_result.state
    return CaptureArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        command="SHAKEANDBAKE_CAPTURE_BELTS",
        parameters=params.as_dict(),
        measurements=list(measurements),
        metadata={
            "planned_motion_envelope": {
                "min_x": envelope.min_x,
                "max_x": envelope.max_x,
                "min_y": envelope.min_y,
                "max_y": envelope.max_y,
            },
            "probe_point": list(state.probe_point) if state.probe_point else None,
            "axes_map": state.axes_map,
            "input_shaper_state": dict(state.input_shaper_state),
            "velocity_limit_state": dict(state.velocity_limit_state),
            "fan_heater_chamber_state": {
                "fans": dict(state.fan_state),
                "heaters": dict(state.heater_state),
                "chamber": dict(state.chamber_state),
            },
            "accelerometer_identity": state.accelerometer_identity,
            "preflight_warnings": [finding.code for finding in preflight_result.warnings],
            "restoration_status": {
                "ok": restoration_status.ok,
                "input_shaper_restored": restoration_status.input_shaper_restored,
                "velocity_limits_restored": restoration_status.velocity_limits_restored,
                "errors": list(restoration_status.errors),
            },
            "orientation_validation_summary": dict(state.orientation_validation_summary),
        },
    )


def _output_path(params: ShaperCaptureParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"shaper-{'-'.join(params.axes)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
    return str(output_dir / name)


def _belt_output_path(params: BeltCaptureParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"belts-a-b-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
    return str(output_dir / name)


def _format_preflight_result(result: Any) -> str:
    lines = [f"Shake&Bake preflight: {'ready' if result.ready else 'not-ready'}"]
    lines.append("supported_axes=" + ",".join(axis.upper() for axis in result.supported_axes))
    if result.state.probe_point:
        lines.append(f"probe_point={result.state.probe_point}")
    if result.state.accelerometer_identity:
        lines.append(f"accelerometer={result.state.accelerometer_identity}")
    if result.blocking_findings:
        lines.append("blocking=" + ",".join(finding.code for finding in result.blocking_findings))
    if result.warnings:
        lines.append("warnings=" + ",".join(finding.code for finding in result.warnings))
    if result.state.orientation_validation_summary:
        orientation = result.state.orientation_validation_summary
        lines.append(f"orientation_status={orientation.get('status')}")
        lines.append(f"orientation_axes_map={orientation.get('configured_axes_map')}")
    return "\n".join(lines)


def _call_or_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    value = getattr(obj, name, default)
    return value() if callable(value) else value


def _public_data(key: str, value: Any) -> bool:
    return not key.startswith("_") and not callable(value)
