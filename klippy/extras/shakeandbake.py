from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shakeandbake_capture import (
    DEFAULT_PHASES,
    PHASE_BASELINE,
    PHASE_SHAPER,
    PHASE_SPEED_PROFILE,
    PHASE_STRESS,
    SPEED_LIMIT_COMMAND,
    SPEED_LIMIT_METADATA_KEY,
    CaptureArtifact,
    ClosedLoopObservation,
    MeasurementBlock,
    RecommendationInputs,
    SafetyStop,
    Sample,
    SpeedLimitCandidate,
    SpeedLimitPhase,
    SpeedProfilePlan,
    TriggerDrift,
    TriggerObservation,
    speed_limit_metadata,
    speed_profile_directions,
    write_capture_artifact,
)
from shakeandbake_max4 import AdapterSnapshot, MotionEnvelope, PreflightRequest, ResourceThresholds, run_preflight
from shakeandbake_max4.config import DEFAULT_MAX4_XY_BOUNDS, Max4ConfigSummary, parse_max4_config

SUPPORTED_SHAPER_AXES = ("x", "y")
BELT_PATH_DIRECTIONS = {
    "A": (1, -1, 0),
    "B": (1, 1, 0),
}
STATIC_EXCITE_DIRECTIONS = {
    "X": (1, 0, 0),
    "Y": (0, 1, 0),
    "A": (1, -1, 0),
    "B": (1, 1, 0),
}
COMMAND_HELP = {
    "SHAKEANDBAKE_PREFLIGHT": "Report Shake&Bake Max 4 preflight readiness and metadata.",
    "SHAKEANDBAKE_CAPTURE_SHAPER": "Capture raw X/Y shaper accelerometer data for external analysis.",
    "SHAKEANDBAKE_CAPTURE_BELTS": "Capture raw CoreXY A/B belt-path accelerometer data for external analysis.",
    SPEED_LIMIT_COMMAND: "Capture Max 4 speed-limit evidence for external analysis.",
    "SHAKEANDBAKE_EXCITE": "Run fixed-frequency X/Y/A/B excitation with optional raw accelerometer recording.",
}
DEFAULT_OUTPUT_DIR = "shakeandbake-captures"


class CommandError(Exception):
    pass


class _ResonanceAxis:
    def __init__(self, axis: str):
        self.axis = axis.lower()
        self.direction = (1.0, 0.0) if self.axis == "x" else (0.0, 1.0)

    def get_name(self) -> str:
        return self.axis

    def get_point(self, distance: float) -> Tuple[float, float]:
        return (self.direction[0] * distance, self.direction[1] * distance)


class _ResonanceGCmd:
    def __init__(self, adapter: "KlipperAdapter", params: Mapping[str, Any]):
        self.adapter = adapter
        self.params = {str(key).lower(): value for key, value in params.items()}

    def get_float(self, key: str, default: Any = None, **_kwargs: Any) -> float:
        return float(self.params.get(key.lower(), default))

    def get_int(self, key: str, default: Any = None, **_kwargs: Any) -> int:
        return int(self.params.get(key.lower(), default))

    def respond_info(self, message: str) -> None:
        self.adapter.respond(None, message)

    def error(self, message: str) -> CommandError:
        return CommandError(message)


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
class StaticExciteParams:
    axis: str
    direction: Tuple[int, int, int]
    frequency: float
    duration: float
    accel_per_hz: float
    travel_speed: float
    accel_chip: Optional[str]
    record: bool
    output_dir: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis,
            "direction_vector": list(self.direction),
            "frequency": self.frequency,
            "duration": self.duration,
            "accel_per_hz": self.accel_per_hz,
            "travel_speed": self.travel_speed,
            "accel_chip": self.accel_chip,
            "record": int(self.record),
            "output_dir": self.output_dir,
        }


@dataclass(frozen=True)
class SpeedLimitCaptureParams:
    max_speed: float
    speed_increment: float
    accel_min: float
    accel_max: float
    accel_increment: float
    profile_accel: float
    travel_speed: float
    profile_segment_length: float
    margin: float
    endstop_samples: int
    max_drift: float
    max_candidates: int
    accel_chip: Optional[str]
    output_dir: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_speed": self.max_speed,
            "speed_increment": self.speed_increment,
            "accel_min": self.accel_min,
            "accel_max": self.accel_max,
            "accel_increment": self.accel_increment,
            "profile_accel": self.profile_accel,
            "travel_speed": self.travel_speed,
            "profile_segment_length": self.profile_segment_length,
            "margin": self.margin,
            "endstop_samples": self.endstop_samples,
            "max_drift": self.max_drift,
            "max_candidates": self.max_candidates,
            "accel_chip": self.accel_chip,
            "output_dir": self.output_dir,
        }


@dataclass(frozen=True)
class StressCandidatePlan:
    candidate_id: str
    velocity: float
    acceleration: float
    directions: Tuple[str, ...]
    repetitions: int
    segment_length: float
    envelope: MotionEnvelope


@dataclass(frozen=True)
class SpeedProfileMeasurementPlan:
    speed: float
    direction_label: str
    angle_degrees: float
    direction_vector: Tuple[int, int, int]
    segment_length: float


@dataclass(frozen=True)
class SpeedLimitPlan:
    phases: Tuple[SpeedLimitPhase, ...]
    candidates: Tuple[StressCandidatePlan, ...]
    speed_profile_measurements: Tuple[SpeedProfileMeasurementPlan, ...]
    speed_profile_plan: SpeedProfilePlan
    envelope: MotionEnvelope


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
        self.gcode = None
        self.toolhead = None
        self.input_shaper = None
        self.resonance_tester = None
        self.virtual_sd = None
        self.pause_resume = None
        self.accelerometer = None
        self.refresh_objects()

    def refresh_objects(self) -> None:
        self.gcode = self.lookup_object("gcode", required=False) or self.gcode
        self.toolhead = self.lookup_object("toolhead", required=False) or self.toolhead
        self.input_shaper = self.lookup_object("input_shaper", required=False) or self.input_shaper
        self.resonance_tester = self.lookup_object("resonance_tester", required=False) or self.resonance_tester
        self.virtual_sd = self.lookup_object("virtual_sdcard", required=False) or self.virtual_sd
        self.pause_resume = self.lookup_object("pause_resume", required=False) or self.pause_resume

    def register_commands(self, owner: "ShakeAndBake") -> None:
        self.refresh_objects()
        if self.gcode is None or not hasattr(self.gcode, "register_command"):
            raise CommandError("required Klipper gcode object is unavailable")
        self._register_command("SHAKEANDBAKE_PREFLIGHT", owner.cmd_preflight)
        self._register_command("SHAKEANDBAKE_CAPTURE_SHAPER", owner.cmd_capture_shaper)
        self._register_command("SHAKEANDBAKE_CAPTURE_BELTS", owner.cmd_capture_belts)
        self._register_command(SPEED_LIMIT_COMMAND, owner.cmd_capture_speed_limits)
        self._register_command("SHAKEANDBAKE_EXCITE", owner.cmd_excite)

    def _register_command(self, name: str, callback: Any) -> None:
        wrapped = self._command_wrapper(callback)
        try:
            self.gcode.register_command(name, wrapped, desc=COMMAND_HELP[name])
        except TypeError:
            self.gcode.register_command(name, wrapped)

    def _command_wrapper(self, callback: Any) -> Any:
        def wrapped(gcmd: Any) -> None:
            try:
                callback(gcmd)
            except CommandError as exc:
                error = getattr(gcmd, "error", None)
                if callable(error):
                    raise error(str(exc))
                raise

        return wrapped

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
        self.refresh_objects()
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
        self.refresh_objects()
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

    def require_homed_axes(self, axes: Sequence[str]) -> None:
        homed_axes = self._homed_axes()
        missing = [axis.lower() for axis in axes if axis.lower() not in homed_axes]
        if missing:
            raise CommandError("printer axes must be homed before Shake&Bake capture: " + ",".join(axis.upper() for axis in missing))

    def _homed_axes(self) -> str:
        reactor = getattr(self.printer, "get_reactor", lambda: None)()
        monotonic = getattr(reactor, "monotonic", None) if reactor is not None else None
        eventtime = monotonic() if callable(monotonic) else 0.0
        for obj in (self.toolhead, self.lookup_object("gcode_move", required=False)):
            if obj is None:
                continue
            get_status = getattr(obj, "get_status", None)
            if callable(get_status):
                try:
                    status = get_status(eventtime)
                except TypeError:
                    status = get_status()
                if isinstance(status, Mapping) and isinstance(status.get("homed_axes"), str):
                    return status["homed_axes"].lower()
            homed_axes = getattr(obj, "homed_axes", None)
            if isinstance(homed_axes, str):
                return homed_axes.lower()
        return ""

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
        payload = params.as_dict()
        move = getattr(self.resonance_tester, "run_axis", None)
        if callable(move):
            def motion() -> None:
                move(axis=axis, params=payload)

            return self._capture_axis_samples(accelerometer, axis, payload, motion)
        if self._has_resonance_test_api():
            return self._capture_resonance_test_samples(accelerometer, axis, payload)
        raise CommandError("resonance motion method is unavailable")

    def _has_resonance_test_api(self) -> bool:
        test = getattr(self.resonance_tester, "test", None)
        return callable(getattr(test, "prepare_test", None)) and callable(getattr(test, "run_test", None))

    def _capture_resonance_test_samples(self, accelerometer: Any, axis: str, params: Mapping[str, Any]) -> List[Sample]:
        start_client = getattr(accelerometer, "start_internal_client", None)
        if not callable(start_client):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        self._move_to_resonance_point()
        client = start_client()
        finished = False
        try:
            gcmd = _ResonanceGCmd(self, params)
            test = self.resonance_tester.test
            test.prepare_test(gcmd)
            test.run_test(_ResonanceAxis(axis), gcmd)
            finish = getattr(client, "finish_measurements", None)
            if callable(finish):
                finish()
                finished = True
            get_samples = getattr(client, "get_samples", None)
            if not callable(get_samples):
                raise CommandError("accelerometer internal client sample method is unavailable")
            return [Sample.from_value(row) for row in get_samples()]
        finally:
            if not finished:
                finish = getattr(client, "finish_measurements", None)
                if callable(finish):
                    try:
                        finish()
                    except Exception:
                        pass

    def _move_to_resonance_point(self) -> None:
        test = getattr(self.resonance_tester, "test", None)
        get_points = getattr(test, "get_start_test_points", None)
        if not callable(get_points):
            return
        points = get_points()
        if not points:
            return
        if self.toolhead is None:
            raise CommandError("toolhead object is unavailable")
        move_speed = float(getattr(self.resonance_tester, "move_speed", 50.0) or 50.0)
        manual_move = getattr(self.toolhead, "manual_move", None)
        if not callable(manual_move):
            raise CommandError("toolhead manual_move method is unavailable")
        manual_move(points[0], move_speed)
        wait_moves = getattr(self.toolhead, "wait_moves", None)
        if callable(wait_moves):
            wait_moves()
        dwell = getattr(self.toolhead, "dwell", None)
        if callable(dwell):
            dwell(0.500)

    def _capture_axis_samples(self, accelerometer: Any, axis: str, params: Mapping[str, Any], motion: Any) -> List[Sample]:
        acquire = getattr(accelerometer, "acquire_samples", None) or getattr(accelerometer, "read_samples", None)
        if callable(acquire):
            motion()
            raw_samples = acquire(axis=axis, params=params)
            return [Sample.from_value(row) for row in raw_samples]
        start_client = getattr(accelerometer, "start_internal_client", None)
        if not callable(start_client):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        client = start_client()
        finished = False
        try:
            motion()
            finish = getattr(client, "finish_measurements", None)
            if callable(finish):
                finish()
                finished = True
            get_samples = getattr(client, "get_samples", None)
            if not callable(get_samples):
                raise CommandError("accelerometer internal client sample method is unavailable")
            return [Sample.from_value(row) for row in get_samples()]
        finally:
            if not finished:
                finish = getattr(client, "finish_measurements", None)
                if callable(finish):
                    try:
                        finish()
                    except Exception:
                        pass

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

    def run_static_excitation(self, params: StaticExciteParams) -> None:
        runner = getattr(self.resonance_tester, "run_static_frequency", None)
        if callable(runner):
            runner(axis=params.axis, direction=params.direction, params=params.as_dict())
            return
        runner = getattr(self.resonance_tester, "run_axis", None)
        if callable(runner):
            runner(axis=params.axis.lower(), params=params.as_dict())

    def record_static_samples(self, params: StaticExciteParams) -> List[Sample]:
        accelerometer = self._accelerometer(params.accel_chip)
        if accelerometer is None:
            raise CommandError("accelerometer is unavailable")
        acquire = getattr(accelerometer, "acquire_samples", None) or getattr(accelerometer, "read_samples", None)
        if not callable(acquire):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        raw_samples = acquire(axis=params.axis.lower(), params=params.as_dict())
        return [Sample.from_value(row) for row in raw_samples]

    def scan_endstop_trigger(self, axis: str, sample_index: int, params: SpeedLimitCaptureParams, config: Max4ConfigSummary) -> TriggerObservation:
        scanner = getattr(self.toolhead, "scan_endstop_trigger", None) or getattr(self.printer, "scan_endstop_trigger", None)
        side, coordinate = _configured_endstop(axis, config)
        timestamp = datetime.now(timezone.utc).isoformat()
        if callable(scanner):
            raw = scanner(axis=axis, speed=params.travel_speed, sample_index=sample_index)
            if isinstance(raw, Mapping):
                return TriggerObservation(
                    axis=axis,
                    side=str(raw.get("side", side)),
                    commanded_coordinate=float(raw.get("commanded_coordinate", coordinate)),
                    observed_coordinate=_optional_float(raw.get("observed_coordinate", raw.get("coordinate", coordinate))),
                    sample_index=sample_index,
                    scan_speed=float(raw.get("scan_speed", params.travel_speed)),
                    timestamp=str(raw.get("timestamp", timestamp)),
                    available=bool(raw.get("available", True)),
                    diagnostic=raw.get("diagnostic"),
                )
        return TriggerObservation(axis, side, coordinate, coordinate, sample_index, min(params.travel_speed, 50.0), timestamp)

    def snapshot_closed_loop(self, phase: str, candidate_id: Optional[str] = None) -> List[ClosedLoopObservation]:
        observations: List[ClosedLoopObservation] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for axis in ("x", "y"):
            name = f"closed_loop {axis}"
            obj = self.lookup_object(name, required=False) or self.lookup_object(f"closed_loop_{axis}", required=False)
            if obj is None:
                continue
            fields = _status_fields(obj)
            observations.append(ClosedLoopObservation(phase, candidate_id, axis, name, fields, timestamp, unsafe=_closed_loop_unsafe(fields)))
        cl_interface = self.lookup_object("cl_interface", required=False)
        if cl_interface is not None:
            fields = _status_fields(cl_interface)
            observations.append(ClosedLoopObservation(phase, candidate_id, None, "cl_interface", fields, timestamp, unsafe=_closed_loop_unsafe(fields)))
        if not observations:
            observations.append(ClosedLoopObservation(phase, candidate_id, None, "closed_loop", {}, timestamp, available=False, diagnostic="closed_loop_unavailable"))
        return observations

    def run_stress_candidate(self, candidate: StressCandidatePlan, params: SpeedLimitCaptureParams) -> None:
        runner = getattr(self.resonance_tester, "run_speed_limit_candidate", None)
        payload = {
            "candidate_id": candidate.candidate_id,
            "velocity": candidate.velocity,
            "acceleration": candidate.acceleration,
            "directions": list(candidate.directions),
            "repetitions": candidate.repetitions,
            "segment_length": candidate.segment_length,
        }
        if callable(runner):
            runner(params=payload)
            return
        run_axis = getattr(self.resonance_tester, "run_axis", None)
        if callable(run_axis):
            for direction in candidate.directions:
                run_axis(axis=direction.lower(), params=payload)

    def acquire_speed_profile_samples(self, plan: SpeedProfileMeasurementPlan, params: SpeedLimitCaptureParams) -> List[Sample]:
        accelerometer = self._accelerometer(params.accel_chip)
        if accelerometer is None:
            raise CommandError("accelerometer is unavailable")
        payload = {
            **params.as_dict(),
            "speed": plan.speed,
            "direction_label": plan.direction_label,
            "direction_angle": plan.angle_degrees,
            "direction_vector": list(plan.direction_vector),
            "segment_length": plan.segment_length,
        }
        runner = getattr(self.resonance_tester, "run_speed_profile", None)
        if callable(runner):
            runner(params=payload)
        else:
            run_axis = getattr(self.resonance_tester, "run_axis", None)
            if callable(run_axis):
                run_axis(axis="a" if plan.angle_degrees == 45.0 else "b", params=payload)
        acquire = getattr(accelerometer, "acquire_samples", None) or getattr(accelerometer, "read_samples", None)
        if not callable(acquire):
            raise CommandError("accelerometer sample acquisition method is unavailable")
        raw_samples = acquire(axis="a" if plan.angle_degrees == 45.0 else "b", params=payload)
        return [Sample.from_value(row) for row in raw_samples]

    def rehome_xy(self) -> None:
        rehome = getattr(self.toolhead, "rehome_xy", None) or getattr(self.printer, "rehome_xy", None)
        if callable(rehome):
            rehome()

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
        self.adapter.require_homed_axes(params.axes)

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

    def cmd_capture_speed_limits(self, gcmd: Any) -> None:
        params = _parse_speed_limit_params(gcmd, self.max4_config)
        plan = _build_speed_limit_plan(params, self.max4_config)
        preflight_request = PreflightRequest(axes=SUPPORTED_SHAPER_AXES, motion_envelope=plan.envelope, safety_margin_mm=params.margin)
        preflight_result = run_preflight(preflight_request, self.max4_config, self.adapter)
        if preflight_result.blocking_findings:
            codes = ", ".join(finding.code for finding in preflight_result.blocking_findings)
            raise CommandError(f"Shake&Bake speed-limit preflight failed: {codes}")
        feature_errors = self.adapter.feature_errors()
        if feature_errors:
            raise CommandError("Shake&Bake feature detection failed: " + "; ".join(feature_errors))
        self.adapter.respond(
            gcmd,
            "Shake&Bake speed-limit plan: "
            f"phases={','.join(phase.name for phase in plan.phases if phase.enabled)} "
            f"candidates={len(plan.candidates)} speed=0..{params.max_speed:g} accel={params.accel_min:g}..{params.accel_max:g} "
            f"max_drift={params.max_drift:g}",
        )

        trigger_observations: List[TriggerObservation] = []
        closed_loop_observations: List[ClosedLoopObservation] = []
        candidates: List[SpeedLimitCandidate] = []
        safety_stops: List[SafetyStop] = []
        diagnostics: List[Mapping[str, Any]] = []
        measurements: List[MeasurementBlock] = []
        restoration_status = RestorationStatus()
        try:
            with AcquisitionContext(self.adapter, params) as context:
                closed_loop_observations.extend(self.adapter.snapshot_closed_loop(PHASE_BASELINE))
                trigger_observations.extend(_collect_baseline_triggers(self.adapter, params, self.max4_config))
                if not _baseline_available(trigger_observations):
                    safety_stops.append(SafetyStop("missing_baseline", PHASE_BASELINE))
                    diagnostics.append({"code": "missing_baseline", "message": "X/Y trigger baseline is unavailable"})
                else:
                    baseline = _baseline_coordinates(trigger_observations)
                    for candidate_plan in plan.candidates:
                        closed_loop_observations.extend(self.adapter.snapshot_closed_loop(PHASE_STRESS, candidate_plan.candidate_id))
                        unsafe_cl = next((obs for obs in closed_loop_observations if obs.candidate_id == candidate_plan.candidate_id and obs.unsafe), None)
                        if unsafe_cl is not None:
                            stop = SafetyStop("closed_loop_unsafe", PHASE_STRESS, candidate_plan.candidate_id, unsafe_cl.axis, dict(unsafe_cl.fields))
                            safety_stops.append(stop)
                            candidates.append(_candidate_record(candidate_plan, self.max4_config, "stopped", (), stop))
                            self.adapter.rehome_xy()
                            break
                        try:
                            self.adapter.run_stress_candidate(candidate_plan, params)
                            post = _collect_candidate_triggers(self.adapter, params, self.max4_config, candidate_plan.candidate_id)
                            trigger_observations.extend(post)
                            drifts = _trigger_drifts(candidate_plan.candidate_id, baseline, post, params.max_drift)
                            unsafe_drift = next((drift for drift in drifts if not drift.passed), None)
                            if unsafe_drift is not None:
                                stop = SafetyStop("trigger_drift", PHASE_STRESS, candidate_plan.candidate_id, unsafe_drift.axis, unsafe_drift.drift_mm)
                                safety_stops.append(stop)
                                candidates.append(_candidate_record(candidate_plan, self.max4_config, "failed", drifts, stop))
                                self.adapter.rehome_xy()
                                break
                            candidates.append(_candidate_record(candidate_plan, self.max4_config, "passed", drifts, None))
                            self.adapter.rehome_xy()
                        except Exception as exc:
                            stop = SafetyStop("candidate_motion_error", PHASE_STRESS, candidate_plan.candidate_id, observed=str(exc))
                            safety_stops.append(stop)
                            candidates.append(_candidate_record(candidate_plan, self.max4_config, "stopped", (), stop))
                            self.adapter.rehome_xy()
                            raise
                try:
                    for axis in SUPPORTED_SHAPER_AXES:
                        shaper_params = _speed_limit_shaper_params(axis, params)
                        samples = self.adapter.acquire_axis_samples(axis, shaper_params)
                        measurements.append(_measurement_for_axis(axis, samples, shaper_params, self.max4_config))
                except Exception as exc:
                    diagnostics.append({"code": "shaper_phase_failed", "message": str(exc), "phase": PHASE_SHAPER})
                try:
                    for measurement_plan in plan.speed_profile_measurements:
                        samples = self.adapter.acquire_speed_profile_samples(measurement_plan, params)
                        measurements.append(_measurement_for_speed_profile(measurement_plan, samples, params, self.max4_config, preflight_result))
                except Exception as exc:
                    diagnostics.append({"code": "speed_profile_phase_failed", "message": str(exc), "phase": PHASE_SPEED_PROFILE})
            restoration_status = context.restoration_status
        except Exception:
            restoration_status = getattr(locals().get("context", None), "restoration_status", restoration_status)
            raise
        finally:
            if not restoration_status.ok:
                self.adapter.respond(gcmd, "Shake&Bake restoration warnings: " + "; ".join(restoration_status.errors))

        artifact = _speed_limit_capture_artifact(
            params,
            plan,
            measurements,
            candidates,
            trigger_observations,
            closed_loop_observations,
            safety_stops,
            diagnostics,
            self.max4_config,
            preflight_result,
            restoration_status,
        )
        write_result = write_capture_artifact(_speed_limit_output_path(params), artifact)
        if not write_result.ok:
            codes = ", ".join(d.status_code for d in write_result.validation.diagnostics)
            raise CommandError(f"speed-limit capture artifact validation failed: {codes}")
        self.adapter.respond(
            gcmd,
            "Shake&Bake speed-limit capture complete: "
            f"path={write_result.path} phases={','.join(phase.name for phase in plan.phases if phase.enabled)} candidates={len(candidates)}",
        )

    def cmd_excite(self, gcmd: Any) -> None:
        params = _parse_static_excite_params(gcmd, self.max4_config)
        preflight_request = PreflightRequest(axes=("x", "y"), motion_envelope=_static_planned_envelope(self.max4_config), safety_margin_mm=5.0)
        preflight_result = run_preflight(preflight_request, self.max4_config, self.adapter)
        if preflight_result.blocking_findings:
            codes = ", ".join(finding.code for finding in preflight_result.blocking_findings)
            raise CommandError(f"Shake&Bake excitation preflight failed: {codes}")
        feature_errors = self.adapter.feature_errors()
        if params.record and feature_errors:
            raise CommandError("Shake&Bake feature detection failed: " + "; ".join(feature_errors))
        restoration_status = RestorationStatus()
        samples: List[Sample] = []
        try:
            with AcquisitionContext(self.adapter, params) as context:
                self.adapter.run_static_excitation(params)
                if params.record:
                    samples = self.adapter.record_static_samples(params)
            restoration_status = context.restoration_status
        except Exception:
            restoration_status = getattr(locals().get("context", None), "restoration_status", restoration_status)
            raise
        finally:
            if not restoration_status.ok:
                self.adapter.respond(gcmd, "Shake&Bake restoration warnings: " + "; ".join(restoration_status.errors))
        if params.record:
            measurement = _measurement_for_static_excitation(params, samples, self.max4_config)
            artifact = _static_capture_artifact(params, [measurement], self.max4_config, preflight_result, restoration_status)
            write_result = write_capture_artifact(_static_output_path(params), artifact)
            if not write_result.ok:
                codes = ", ".join(d.status_code for d in write_result.validation.diagnostics)
                raise CommandError(f"static-frequency capture artifact validation failed: {codes}")
            self.adapter.respond(gcmd, f"Shake&Bake excitation complete: path={write_result.path} measurements={measurement.name}")
        else:
            self.adapter.respond(gcmd, f"Shake&Bake excitation complete: axis={params.axis} frequency={params.frequency} duration={params.duration}")


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


def _parse_static_excite_params(gcmd: Any, config: Max4ConfigSummary) -> StaticExciteParams:
    axis = str(_gcmd_get(gcmd, "AXIS", "")).upper()
    if axis not in STATIC_EXCITE_DIRECTIONS:
        raise CommandError("Max 4 Shake&Bake excitation supports AXIS=X, AXIS=Y, AXIS=A, or AXIS=B only")
    frequency = _gcmd_float(gcmd, "FREQUENCY", None, above=0.0)
    duration = _gcmd_float(gcmd, "DURATION", None, above=0.0)
    if frequency > 200.0:
        raise CommandError("FREQUENCY exceeds the supported static excitation limit")
    if duration > 120.0:
        raise CommandError("DURATION exceeds the supported static excitation limit")
    accel_per_hz = _gcmd_float(gcmd, "ACCEL_PER_HZ", config.resonance_tester.accel_per_hz or 75.0, above=0.0)
    travel_speed = _gcmd_float(gcmd, "TRAVEL_SPEED", config.printer.max_velocity or 100.0, above=0.0)
    accel_chip = _gcmd_get(gcmd, "ACCEL_CHIP", config.accelerometer_identity)
    record = _gcmd_bool(gcmd, "RECORD", False)
    output_dir = _gcmd_get(gcmd, "OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    return StaticExciteParams(axis, STATIC_EXCITE_DIRECTIONS[axis], frequency, duration, accel_per_hz, travel_speed, accel_chip, record, output_dir)


def _parse_speed_limit_params(gcmd: Any, config: Max4ConfigSummary) -> SpeedLimitCaptureParams:
    if (config.printer.kinematics or "corexy").lower() != "corexy":
        raise CommandError("SHAKEANDBAKE_CAPTURE_SPEED_LIMITS supports QIDI Max 4 CoreXY kinematics only")
    axis_raw = _gcmd_get(gcmd, "AXIS", None)
    if axis_raw is not None and str(axis_raw).upper() not in ("X", "Y", "XY", "ALL"):
        raise CommandError("SHAKEANDBAKE_CAPTURE_SPEED_LIMITS supports X/Y CoreXY motion only; Z-axis parameters are unsupported")
    if str(axis_raw).upper() == "Z":
        raise CommandError("SHAKEANDBAKE_CAPTURE_SPEED_LIMITS supports X/Y CoreXY motion only; Z-axis parameters are unsupported")
    configured_max_speed = config.printer.max_velocity or 800.0
    configured_max_accel = config.printer.max_accel or 30000.0
    max_speed = _gcmd_float(gcmd, "MAX_SPEED", min(300.0, configured_max_speed), above=0.0)
    speed_increment = _gcmd_float(gcmd, "SPEED_INCREMENT", 100.0, above=0.0)
    accel_min = _gcmd_float(gcmd, "ACCEL_MIN", min(5000.0, configured_max_accel), above=0.0)
    accel_max = _gcmd_float(gcmd, "ACCEL_MAX", min(15000.0, configured_max_accel), above=0.0)
    accel_increment = _gcmd_float(gcmd, "ACCEL_INCREMENT", 5000.0, above=0.0)
    profile_accel = _gcmd_float(gcmd, "PROFILE_ACCEL", min(10000.0, configured_max_accel), above=0.0)
    travel_speed = _gcmd_float(gcmd, "TRAVEL_SPEED", min(max_speed, configured_max_speed), above=0.0)
    profile_segment_length = _gcmd_float(gcmd, "SIZE", 60.0, above=0.0)
    margin = _gcmd_float(gcmd, "MARGIN", 5.0, above=0.0)
    endstop_samples = _gcmd_int(gcmd, "ENDSTOP_SAMPLES", 3, min_value=1)
    max_drift = _gcmd_float(gcmd, "MAX_DRIFT", 0.05, above=0.0)
    max_candidates = _gcmd_int(gcmd, "MAX_CANDIDATES", 24, min_value=1)
    accel_chip = _gcmd_get(gcmd, "ACCEL_CHIP", config.accelerometer_identity)
    output_dir = _gcmd_get(gcmd, "OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    if max_speed > configured_max_speed:
        raise CommandError("MAX_SPEED exceeds configured printer max_velocity")
    if accel_max > configured_max_accel:
        raise CommandError("ACCEL_MAX exceeds configured printer max_accel")
    if accel_min > accel_max:
        raise CommandError("ACCEL_MIN must be less than or equal to ACCEL_MAX")
    params = SpeedLimitCaptureParams(
        max_speed,
        speed_increment,
        accel_min,
        accel_max,
        accel_increment,
        profile_accel,
        travel_speed,
        profile_segment_length,
        margin,
        endstop_samples,
        max_drift,
        max_candidates,
        accel_chip,
        output_dir,
    )
    plan = _build_speed_limit_plan(params, config)
    if len(plan.candidates) > max_candidates:
        raise CommandError("speed-limit candidate grid exceeds MAX_CANDIDATES")
    return params


def _gcmd_get(gcmd: Any, key: str, default: Any) -> Any:
    getter = getattr(gcmd, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(gcmd, key.lower(), default)


def _gcmd_float(gcmd: Any, key: str, default: Optional[float], above: Optional[float] = None) -> float:
    getter = getattr(gcmd, "get_float", None)
    try:
        if callable(getter):
            return float(getter(key, default, above=above))
        raw = _gcmd_get(gcmd, key, default)
        if raw is None:
            raise ValueError(f"{key} is required")
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise CommandError(f"invalid {key}: {exc}") from exc
    if above is not None and value <= above:
        raise CommandError(f"{key} must be greater than {above}")
    return value


def _gcmd_bool(gcmd: Any, key: str, default: bool) -> bool:
    value = _gcmd_get(gcmd, key, int(default))
    if isinstance(value, bool):
        return value
    if str(value).strip() in ("1", "true", "TRUE", "yes", "YES"):
        return True
    if str(value).strip() in ("0", "false", "FALSE", "no", "NO"):
        return False
    raise CommandError(f"{key} must be 0 or 1")


def _gcmd_int(gcmd: Any, key: str, default: int, min_value: Optional[int] = None) -> int:
    value = _gcmd_get(gcmd, key, default)
    try:
        parsed = int(float(value))
    except (TypeError, ValueError) as exc:
        raise CommandError(f"invalid {key}: {exc}") from exc
    if min_value is not None and parsed < min_value:
        raise CommandError(f"{key} must be at least {min_value}")
    return parsed


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


def _static_planned_envelope(config: Max4ConfigSummary) -> MotionEnvelope:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    return MotionEnvelope.around_point(point, radius=10.0)


def _build_speed_limit_plan(params: SpeedLimitCaptureParams, config: Max4ConfigSummary) -> SpeedLimitPlan:
    point = config.resonance_tester.primary_probe_point or (162.5, 162.5, 10.0)
    radius = max(10.0, params.profile_segment_length / 2.0 + params.margin)
    envelope = MotionEnvelope.around_point(point, radius=radius)
    speeds = _range_values(params.speed_increment, params.max_speed, params.speed_increment)
    accels = _range_values(params.accel_min, params.accel_max, params.accel_increment)
    directions = ("x", "y", "diag_45", "diag_135")
    candidates: List[StressCandidatePlan] = []
    index = 1
    for accel in accels:
        for speed in speeds:
            candidates.append(
                StressCandidatePlan(
                    candidate_id=f"v{int(speed)}-a{int(accel)}-{index:03d}",
                    velocity=speed,
                    acceleration=accel,
                    directions=directions,
                    repetitions=2,
                    segment_length=params.profile_segment_length,
                    envelope=envelope,
                )
            )
            index += 1
    if len(candidates) > params.max_candidates:
        raise CommandError("speed-limit candidate grid exceeds MAX_CANDIDATES")
    speed_profile_dirs = speed_profile_directions()
    profile_measurements = tuple(
        SpeedProfileMeasurementPlan(
            speed=speed,
            direction_label=str(direction["label"]),
            angle_degrees=float(direction["angle_degrees"]),
            direction_vector=tuple(int(item) for item in direction["unit_vector"]),
            segment_length=params.profile_segment_length,
        )
        for speed in speeds
        for direction in speed_profile_dirs
    )
    speed_profile_plan = SpeedProfilePlan(speeds, speed_profile_dirs, params.profile_accel, params.travel_speed, params.profile_segment_length, 64)
    phases = tuple(SpeedLimitPhase(name=name) for name in DEFAULT_PHASES)
    return SpeedLimitPlan(phases, tuple(candidates), profile_measurements, speed_profile_plan, envelope)


def _range_values(start: float, end: float, increment: float) -> Tuple[float, ...]:
    values = []
    value = start
    guard = 0
    while value <= end + 1e-9:
        values.append(round(value, 6))
        value += increment
        guard += 1
        if guard > 10000:
            raise CommandError("range generation exceeded guard limit")
    return tuple(values)


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


def _measurement_for_speed_profile(
    plan: SpeedProfileMeasurementPlan,
    samples: Sequence[Sample],
    params: SpeedLimitCaptureParams,
    config: Max4ConfigSummary,
    preflight_result: Any,
) -> MeasurementBlock:
    state = preflight_result.state
    return MeasurementBlock(
        name=f"speed_profile_{int(plan.angle_degrees)}_{int(plan.speed)}",
        axis="speed_profile",
        sensor=params.accel_chip or config.accelerometer_identity,
        sample_rate_hz=None,
        samples=list(samples),
        metadata={
            "kind": "speed_profile",
            "speed": plan.speed,
            "direction_label": plan.direction_label,
            "direction_angle": plan.angle_degrees,
            "direction_vector": list(plan.direction_vector),
            "segment_length": plan.segment_length,
            "acceleration": params.profile_accel,
            "travel_speed": params.travel_speed,
            "accelerometer_object": params.accel_chip or config.accelerometer_identity,
            "probe_point": list(state.probe_point) if state.probe_point else None,
            "axes_map": state.axes_map,
            "preflight_warnings": [finding.code for finding in preflight_result.warnings],
        },
    )


def _measurement_for_static_excitation(
    params: StaticExciteParams,
    samples: Sequence[Sample],
    config: Max4ConfigSummary,
) -> MeasurementBlock:
    return MeasurementBlock(
        name=f"static_{params.axis.lower()}",
        axis=params.axis.lower(),
        sensor=params.accel_chip or config.accelerometer_identity,
        sample_rate_hz=None,
        samples=list(samples),
        metadata={
            "axis_label": params.axis,
            "direction_vector": list(params.direction),
            "frequency": params.frequency,
            "duration": params.duration,
            "accel_per_hz": params.accel_per_hz,
            "travel_speed": params.travel_speed,
            "accelerometer_object": params.accel_chip or config.accelerometer_identity,
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


def _speed_limit_capture_artifact(
    params: SpeedLimitCaptureParams,
    plan: SpeedLimitPlan,
    measurements: Sequence[MeasurementBlock],
    candidates: Sequence[SpeedLimitCandidate],
    trigger_observations: Sequence[TriggerObservation],
    closed_loop_observations: Sequence[ClosedLoopObservation],
    safety_stops: Sequence[SafetyStop],
    diagnostics: Sequence[Mapping[str, Any]],
    config: Max4ConfigSummary,
    preflight_result: Any,
    restoration_status: RestorationStatus,
) -> CaptureArtifact:
    envelope = plan.envelope
    state = preflight_result.state
    metadata = {
        "planned_motion_envelope": {"min_x": envelope.min_x, "max_x": envelope.max_x, "min_y": envelope.min_y, "max_y": envelope.max_y},
        "probe_point": list(state.probe_point) if state.probe_point else None,
        "axes_map": state.axes_map,
        "input_shaper_state": dict(state.input_shaper_state),
        "velocity_limit_state": dict(state.velocity_limit_state),
        "square_corner_velocity": dict(state.velocity_limit_state).get("square_corner_velocity"),
        "fan_heater_chamber_state": {"fans": dict(state.fan_state), "heaters": dict(state.heater_state), "chamber": dict(state.chamber_state)},
        "accelerometer_identity": state.accelerometer_identity,
        "preflight_warnings": [finding.code for finding in preflight_result.warnings],
        "host_resources": {"host_load": state.host_load, "free_memory_mb": state.free_memory_mb, "free_disk_mb": state.free_disk_mb},
        "restoration_status": {"ok": restoration_status.ok, "input_shaper_restored": restoration_status.input_shaper_restored, "velocity_limits_restored": restoration_status.velocity_limits_restored, "errors": list(restoration_status.errors)},
        "orientation_validation_summary": dict(state.orientation_validation_summary),
    }
    metadata[SPEED_LIMIT_METADATA_KEY] = speed_limit_metadata(
        phases=tuple(SpeedLimitPhase(phase.name, phase.enabled, "complete") for phase in plan.phases),
        candidates=candidates,
        trigger_observations=trigger_observations,
        closed_loop_observations=closed_loop_observations,
        safety_stops=safety_stops,
        speed_profile_plan=plan.speed_profile_plan,
        recommendation_inputs=RecommendationInputs(max_drift_mm=params.max_drift),
        diagnostics=diagnostics,
    )
    metadata[SPEED_LIMIT_METADATA_KEY]["baseline"] = _baseline_summary(trigger_observations, params.max_drift)
    return CaptureArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        command=SPEED_LIMIT_COMMAND,
        parameters=params.as_dict(),
        measurements=list(measurements),
        metadata=metadata,
    )


def _static_capture_artifact(
    params: StaticExciteParams,
    measurements: Sequence[MeasurementBlock],
    config: Max4ConfigSummary,
    preflight_result: Any,
    restoration_status: RestorationStatus,
) -> CaptureArtifact:
    envelope = _static_planned_envelope(config)
    state = preflight_result.state
    return CaptureArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        command="SHAKEANDBAKE_EXCITE",
        parameters=params.as_dict(),
        measurements=list(measurements),
        metadata={
            "planned_motion_envelope": {"min_x": envelope.min_x, "max_x": envelope.max_x, "min_y": envelope.min_y, "max_y": envelope.max_y},
            "probe_point": list(state.probe_point) if state.probe_point else None,
            "axes_map": state.axes_map,
            "input_shaper_state": dict(state.input_shaper_state),
            "velocity_limit_state": dict(state.velocity_limit_state),
            "fan_heater_chamber_state": {"fans": dict(state.fan_state), "heaters": dict(state.heater_state), "chamber": dict(state.chamber_state)},
            "accelerometer_identity": state.accelerometer_identity,
            "preflight_warnings": [finding.code for finding in preflight_result.warnings],
            "restoration_status": {"ok": restoration_status.ok, "input_shaper_restored": restoration_status.input_shaper_restored, "velocity_limits_restored": restoration_status.velocity_limits_restored, "errors": list(restoration_status.errors)},
            "orientation_validation_summary": dict(state.orientation_validation_summary),
        },
        tool="static-frequency",
    )


def _output_path(params: ShaperCaptureParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"shaper-{'-'.join(params.axes)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
    return str(output_dir / name)


def _belt_output_path(params: BeltCaptureParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"belts-a-b-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
    return str(output_dir / name)


def _static_output_path(params: StaticExciteParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"static-{params.axis.lower()}-{params.frequency:g}hz-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
    return str(output_dir / name)


def _speed_limit_output_path(params: SpeedLimitCaptureParams) -> str:
    output_dir = Path(params.output_dir)
    name = f"speed-limits-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sbcapture.json"
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


def _collect_baseline_triggers(adapter: KlipperAdapter, params: SpeedLimitCaptureParams, config: Max4ConfigSummary) -> List[TriggerObservation]:
    observations: List[TriggerObservation] = []
    for axis in SUPPORTED_SHAPER_AXES:
        for index in range(params.endstop_samples):
            observations.append(adapter.scan_endstop_trigger(axis, index, params, config))
    return observations


def _collect_candidate_triggers(
    adapter: KlipperAdapter, params: SpeedLimitCaptureParams, config: Max4ConfigSummary, candidate_id: str
) -> List[TriggerObservation]:
    observations = []
    for axis in SUPPORTED_SHAPER_AXES:
        obs = adapter.scan_endstop_trigger(axis, 0, params, config)
        observations.append(
            TriggerObservation(
                obs.axis,
                obs.side,
                obs.commanded_coordinate,
                obs.observed_coordinate,
                obs.sample_index,
                obs.scan_speed,
                obs.timestamp,
                obs.available,
                PHASE_STRESS,
                candidate_id,
                obs.diagnostic,
            )
        )
    return observations


def _baseline_available(observations: Sequence[TriggerObservation]) -> bool:
    axes = {obs.axis for obs in observations if obs.phase == PHASE_BASELINE and obs.available and obs.observed_coordinate is not None}
    return set(SUPPORTED_SHAPER_AXES).issubset(axes)


def _baseline_coordinates(observations: Sequence[TriggerObservation]) -> Mapping[str, float]:
    result: Dict[str, float] = {}
    for axis in SUPPORTED_SHAPER_AXES:
        values = [float(obs.observed_coordinate) for obs in observations if obs.axis == axis and obs.available and obs.observed_coordinate is not None]
        if values:
            result[axis] = sum(values) / len(values)
    return result


def _baseline_summary(observations: Sequence[TriggerObservation], threshold: float) -> Mapping[str, Any]:
    summary: Dict[str, Any] = {"threshold_mm": threshold, "axes": {}}
    for axis in SUPPORTED_SHAPER_AXES:
        values = [float(obs.observed_coordinate) for obs in observations if obs.axis == axis and obs.phase == PHASE_BASELINE and obs.available and obs.observed_coordinate is not None]
        if values:
            summary["axes"][axis] = {"mean": sum(values) / len(values), "spread_mm": max(values) - min(values), "sample_count": len(values)}
        else:
            summary["axes"][axis] = {"mean": None, "spread_mm": None, "sample_count": 0}
    return summary


def _trigger_drifts(candidate_id: str, baseline: Mapping[str, float], post: Sequence[TriggerObservation], threshold: float) -> Tuple[TriggerDrift, ...]:
    drifts = []
    for obs in post:
        base = baseline.get(obs.axis)
        observed = obs.observed_coordinate if obs.available else None
        drift = abs(float(observed) - base) if base is not None and observed is not None else None
        drifts.append(TriggerDrift(obs.axis, candidate_id, base, observed, drift, threshold, drift is not None and drift <= threshold))
    return tuple(drifts)


def _candidate_record(
    candidate: StressCandidatePlan,
    config: Max4ConfigSummary,
    status: str,
    drifts: Sequence[TriggerDrift],
    safety_stop: Optional[SafetyStop],
) -> SpeedLimitCandidate:
    envelope = candidate.envelope
    return SpeedLimitCandidate(
        candidate_id=candidate.candidate_id,
        velocity=candidate.velocity,
        acceleration=candidate.acceleration,
        directions=candidate.directions,
        repetitions=candidate.repetitions,
        segment_length=candidate.segment_length,
        planned_envelope={"min_x": envelope.min_x, "max_x": envelope.max_x, "min_y": envelope.min_y, "max_y": envelope.max_y},
        planner_settings={
            "max_velocity": config.printer.max_velocity,
            "max_accel": config.printer.max_accel,
            "square_corner_velocity": config.printer.square_corner_velocity,
            "min_cruise_ratio": _config_value(config, "printer", "minimum_cruise_ratio"),
        },
        status=status,
        trigger_drift=tuple(drifts),
        safety_stop=safety_stop.to_dict() if safety_stop else None,
    )


def _speed_limit_shaper_params(axis: str, params: SpeedLimitCaptureParams) -> ShaperCaptureParams:
    return ShaperCaptureParams((axis,), 5.0, 120.0, 1.0, params.profile_accel / 100.0, params.travel_speed, params.accel_chip, params.output_dir)


def _configured_endstop(axis: str, config: Max4ConfigSummary) -> Tuple[str, float]:
    data = config.raw_sections.get(f"stepper_{axis}", {})
    positive = str(data.get("homing_positive_dir", "false")).lower() in ("true", "1", "yes")
    side = "max" if positive else "min"
    raw = data.get("position_endstop") or data.get("position_max" if positive else "position_min")
    try:
        coordinate = float(raw) if raw is not None else (config.xy_bounds[1] if axis == "x" else config.xy_bounds[2])
    except ValueError:
        coordinate = config.xy_bounds[1] if axis == "x" else config.xy_bounds[2]
    return side, coordinate


def _config_value(config: Max4ConfigSummary, section: str, key: str) -> Any:
    return config.raw_sections.get(section, {}).get(key)


def _status_fields(obj: Any) -> Mapping[str, Any]:
    status = getattr(obj, "get_status", None)
    if callable(status):
        try:
            value = status(0.0)
        except TypeError:
            value = status()
        if isinstance(value, Mapping):
            return dict(value)
    state = getattr(obj, "state", None)
    if isinstance(state, Mapping):
        return dict(state)
    return {key: value for key, value in getattr(obj, "__dict__", {}).items() if _public_data(key, value)}


def _closed_loop_unsafe(fields: Mapping[str, Any]) -> bool:
    unsafe_keys = ("fault", "alarm", "error", "motor_position_error", "no_response", "phase_loss", "overcurrent", "high_temp_alarm", "stepper_out_of_tolerance_alarm")
    for key, value in fields.items():
        lowered = key.lower()
        if any(marker in lowered for marker in unsafe_keys) and bool(value):
            return True
        if isinstance(value, str) and value.lower() in ("fault", "alarm", "error", "unsafe", "no_response"):
            return True
    return False


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _call_or_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    value = getattr(obj, name, default)
    return value() if callable(value) else value


def _public_data(key: str, value: Any) -> bool:
    return not key.startswith("_") and not callable(value)
