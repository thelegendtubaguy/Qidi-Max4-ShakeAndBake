from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({SUPPORTED_SCHEMA_VERSION})

REQUIRED_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "tool",
        "printer_model",
        "created_at",
        "command",
        "parameters",
        "measurements",
        "metadata",
    }
)

REQUIRED_METADATA_FIELDS = frozenset(
    {
        "planned_motion_envelope",
        "probe_point",
        "axes_map",
        "input_shaper_state",
        "velocity_limit_state",
        "fan_heater_chamber_state",
    }
)

REQUIRED_MEASUREMENT_FIELDS = frozenset({"name", "axis", "sensor", "sample_count", "samples"})
REQUIRED_SAMPLE_COLUMNS = ("time", "accel_x", "accel_y", "accel_z")
DEFAULT_SAMPLE_UNITS = {
    "time": "s",
    "accel_x": "m/s^2",
    "accel_y": "m/s^2",
    "accel_z": "m/s^2",
}
DERIVED_OUTPUT_FIELDS = frozenset(
    {
        "analysis_summary",
        "analysis_summary_path",
        "summary",
        "summary_path",
        "graph",
        "graph_path",
        "graph_paths",
        "report",
        "report_path",
        "proposed_config",
        "proposed_config_path",
        "config_snippet",
    }
)

VALID_STATUS = "valid"
STATUS_UNSUPPORTED_SCHEMA = "unsupported_schema"
STATUS_MISSING_REQUIRED_FIELD = "missing_required_field"
STATUS_INVALID_SAMPLE_SHAPE = "invalid_sample_shape"
STATUS_INSUFFICIENT_SAMPLES = "insufficient_samples"
STATUS_NONMONOTONIC_TIME = "nonmonotonic_time"
STATUS_NONFINITE_SAMPLE = "nonfinite_sample"
STATUS_CONSTANT_SIGNAL = "constant_signal"
STATUS_SAMPLE_RATE_OUT_OF_RANGE = "sample_rate_out_of_range"
STATUS_INVALID_Z_AXIS_CALIBRATION = "invalid_z_axis_calibration"
STATUS_DERIVED_OUTPUT_IN_RAW_CAPTURE = "derived_output_in_raw_capture"
STATUS_IO_ERROR = "io_error"
STATUS_INVALID_JSON = "invalid_json"


@dataclass(frozen=True)
class Sample:
    time: float
    accel_x: float
    accel_y: float
    accel_z: float

    @classmethod
    def from_value(cls, value: Any) -> "Sample":
        if isinstance(value, Mapping):
            return cls(
                time=float(value["time"]),
                accel_x=float(value["accel_x"]),
                accel_y=float(value["accel_y"]),
                accel_z=float(value["accel_z"]),
            )
        row = list(value)
        if len(row) != len(REQUIRED_SAMPLE_COLUMNS):
            raise ValueError("sample row must contain time, accel_x, accel_y, accel_z")
        return cls(float(row[0]), float(row[1]), float(row[2]), float(row[3]))

    def as_row(self) -> List[float]:
        return [self.time, self.accel_x, self.accel_y, self.accel_z]

    def as_dict(self) -> Dict[str, float]:
        return {
            "time": self.time,
            "accel_x": self.accel_x,
            "accel_y": self.accel_y,
            "accel_z": self.accel_z,
        }


@dataclass
class MeasurementBlock:
    name: str
    axis: str
    sensor: str
    samples: List[Sample]
    sample_rate_hz: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    columns: Sequence[str] = REQUIRED_SAMPLE_COLUMNS
    units: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SAMPLE_UNITS))
    sample_count: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MeasurementBlock":
        known = {
            "name",
            "axis",
            "sensor",
            "samples",
            "sample_rate_hz",
            "metadata",
            "columns",
            "units",
            "sample_count",
        }
        samples = [Sample.from_value(row) for row in data.get("samples", [])]
        return cls(
            name=str(data.get("name", "")),
            axis=str(data.get("axis", "")),
            sensor=str(data.get("sensor", "")),
            samples=samples,
            sample_rate_hz=_optional_float(data.get("sample_rate_hz")),
            metadata=dict(data.get("metadata", {})),
            columns=tuple(data.get("columns", REQUIRED_SAMPLE_COLUMNS)),
            units=dict(data.get("units", {})) or dict(DEFAULT_SAMPLE_UNITS),
            sample_count=data.get("sample_count"),
            extra={key: value for key, value in data.items() if key not in known},
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = dict(self.extra)
        data.update(
            {
                "name": self.name,
                "axis": self.axis,
                "sensor": self.sensor,
                "sample_count": self.effective_sample_count,
                "sample_rate_hz": self.sample_rate_hz,
                "columns": list(self.columns),
                "units": dict(self.units),
                "metadata": dict(self.metadata),
                "samples": [sample.as_row() for sample in self.samples],
            }
        )
        return data

    @property
    def effective_sample_count(self) -> int:
        if self.sample_count is None:
            return len(self.samples)
        return int(self.sample_count)


@dataclass
class CaptureArtifact:
    created_at: str
    command: str
    parameters: Dict[str, Any]
    measurements: List[MeasurementBlock]
    metadata: Dict[str, Any]
    schema_version: int = SUPPORTED_SCHEMA_VERSION
    tool: str = "shakeandbake"
    printer_model: str = "qidi_max_4"
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CaptureArtifact":
        known = {
            "schema_version",
            "tool",
            "printer_model",
            "created_at",
            "command",
            "parameters",
            "measurements",
            "metadata",
        }
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            tool=str(data.get("tool", "")),
            printer_model=str(data.get("printer_model", "")),
            created_at=str(data.get("created_at", "")),
            command=str(data.get("command", "")),
            parameters=dict(data.get("parameters", {})),
            measurements=[MeasurementBlock.from_dict(item) for item in data.get("measurements", [])],
            metadata=dict(data.get("metadata", {})),
            extra={key: value for key, value in data.items() if key not in known},
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = dict(self.extra)
        data.update(
            {
                "schema_version": self.schema_version,
                "tool": self.tool,
                "printer_model": self.printer_model,
                "created_at": self.created_at,
                "command": self.command,
                "parameters": dict(self.parameters),
                "metadata": dict(self.metadata),
                "measurements": [measurement.to_dict() for measurement in self.measurements],
            }
        )
        return data


@dataclass(frozen=True)
class ValidationDiagnostic:
    status_code: str
    message: str
    field_path: Optional[str] = None
    measurement_name: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    status: str
    diagnostics: Sequence[ValidationDiagnostic] = ()

    @property
    def valid(self) -> bool:
        return self.status == VALID_STATUS


@dataclass(frozen=True)
class ReadResult:
    artifact: Optional[CaptureArtifact]
    validation: ValidationResult
    path: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.artifact is not None and self.validation.valid


@dataclass(frozen=True)
class WriteResult:
    path: str
    validation: ValidationResult
    metadata_sidecar_path: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.validation.valid


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def sample_rows(rows: Iterable[Sequence[float]]) -> List[Sample]:
    return [Sample.from_value(row) for row in rows]
