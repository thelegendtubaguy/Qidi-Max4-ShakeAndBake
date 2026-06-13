from __future__ import annotations

import math
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from .models import (
    DERIVED_OUTPUT_FIELDS,
    REQUIRED_MEASUREMENT_FIELDS,
    REQUIRED_METADATA_FIELDS,
    REQUIRED_ROOT_FIELDS,
    REQUIRED_SAMPLE_COLUMNS,
    STATUS_CONSTANT_SIGNAL,
    STATUS_DERIVED_OUTPUT_IN_RAW_CAPTURE,
    STATUS_INSUFFICIENT_SAMPLES,
    STATUS_INVALID_SAMPLE_SHAPE,
    STATUS_INVALID_Z_AXIS_CALIBRATION,
    STATUS_MISSING_REQUIRED_FIELD,
    STATUS_NONFINITE_SAMPLE,
    STATUS_NONMONOTONIC_TIME,
    STATUS_SAMPLE_RATE_OUT_OF_RANGE,
    STATUS_UNSUPPORTED_SCHEMA,
    SUPPORTED_SCHEMA_VERSIONS,
    VALID_STATUS,
    CaptureArtifact,
    MeasurementBlock,
    ValidationDiagnostic,
    ValidationResult,
)


def validate_capture_artifact(artifact: CaptureArtifact | Mapping[str, Any]) -> ValidationResult:
    raw = artifact.to_dict() if isinstance(artifact, CaptureArtifact) else dict(artifact)
    diagnostics: List[ValidationDiagnostic] = []

    _validate_required_fields(raw, REQUIRED_ROOT_FIELDS, "$", diagnostics)
    _validate_unsupported_schema(raw, diagnostics)
    _validate_raw_derived_separation(raw, diagnostics)

    metadata = raw.get("metadata")
    if isinstance(metadata, Mapping):
        _validate_required_fields(metadata, REQUIRED_METADATA_FIELDS, "$.metadata", diagnostics)
    elif "metadata" in raw:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_MISSING_REQUIRED_FIELD,
                "metadata must be an object",
                "$.metadata",
            )
        )

    measurements = raw.get("measurements")
    if isinstance(measurements, Sequence) and not isinstance(measurements, (str, bytes, bytearray)):
        for index, measurement in enumerate(measurements):
            if isinstance(measurement, Mapping):
                _validate_measurement(raw, measurement, index, diagnostics)
            else:
                diagnostics.append(
                    ValidationDiagnostic(
                        STATUS_MISSING_REQUIRED_FIELD,
                        "measurement must be an object",
                        f"$.measurements[{index}]",
                    )
                )
    elif "measurements" in raw:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_MISSING_REQUIRED_FIELD,
                "measurements must be a list",
                "$.measurements",
            )
        )

    if diagnostics:
        return ValidationResult(diagnostics[0].status_code, tuple(diagnostics))
    return ValidationResult(VALID_STATUS, ())


def derive_sample_rate_hz(measurement: MeasurementBlock | Mapping[str, Any]) -> Optional[float]:
    samples = measurement.samples if isinstance(measurement, MeasurementBlock) else measurement.get("samples", [])
    times = [_sample_time(sample) for sample in samples]
    if len(times) < 2:
        return None
    duration = times[-1] - times[0]
    if duration <= 0:
        return None
    return (len(times) - 1) / duration


def _validate_required_fields(
    data: Mapping[str, Any], required: Iterable[str], path: str, diagnostics: List[ValidationDiagnostic]
) -> None:
    for field in sorted(required):
        if field not in data:
            diagnostics.append(
                ValidationDiagnostic(
                    STATUS_MISSING_REQUIRED_FIELD,
                    f"missing required field: {field}",
                    f"{path}.{field}",
                )
            )


def _validate_unsupported_schema(raw: Mapping[str, Any], diagnostics: List[ValidationDiagnostic]) -> None:
    schema_version = raw.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_UNSUPPORTED_SCHEMA,
                f"unsupported schema_version: {schema_version!r}",
                "$.schema_version",
            )
        )


def _validate_raw_derived_separation(raw: Mapping[str, Any], diagnostics: List[ValidationDiagnostic]) -> None:
    for field_path in _find_forbidden_fields(raw, "$", DERIVED_OUTPUT_FIELDS):
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_DERIVED_OUTPUT_IN_RAW_CAPTURE,
                "raw capture artifact contains derived analysis output metadata",
                field_path,
            )
        )


def _validate_measurement(
    root: Mapping[str, Any], measurement: Mapping[str, Any], index: int, diagnostics: List[ValidationDiagnostic]
) -> None:
    base_path = f"$.measurements[{index}]"
    name = str(measurement.get("name", f"measurement[{index}]"))

    _validate_required_fields(measurement, REQUIRED_MEASUREMENT_FIELDS, base_path, diagnostics)

    columns = tuple(measurement.get("columns", REQUIRED_SAMPLE_COLUMNS))
    if columns != REQUIRED_SAMPLE_COLUMNS:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INVALID_SAMPLE_SHAPE,
                "measurement columns must be time, accel_x, accel_y, accel_z",
                f"{base_path}.columns",
                name,
            )
        )

    if root.get("printer_model") == "qidi_max_4" and _marks_z_calibration(root, measurement):
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INVALID_Z_AXIS_CALIBRATION,
                "QIDI Max 4 capture artifacts must not mark Z as a calibration target",
                base_path,
                name,
            )
        )

    samples = measurement.get("samples", [])
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes, bytearray)):
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INVALID_SAMPLE_SHAPE,
                "samples must be a list",
                f"{base_path}.samples",
                name,
            )
        )
        return

    if len(samples) < 2:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INSUFFICIENT_SAMPLES,
                "measurement must contain at least two samples",
                f"{base_path}.samples",
                name,
            )
        )
        return

    sample_count = measurement.get("sample_count")
    if sample_count is not None and sample_count != len(samples):
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INVALID_SAMPLE_SHAPE,
                "sample_count must match the number of sample rows",
                f"{base_path}.sample_count",
                name,
            )
        )

    parsed_rows = []
    for sample_index, sample in enumerate(samples):
        row = _sample_row(sample)
        if len(row) != len(REQUIRED_SAMPLE_COLUMNS):
            diagnostics.append(
                ValidationDiagnostic(
                    STATUS_INVALID_SAMPLE_SHAPE,
                    "sample row must contain time, accel_x, accel_y, accel_z",
                    f"{base_path}.samples[{sample_index}]",
                    name,
                )
            )
            continue
        if not all(_is_finite(value) for value in row):
            diagnostics.append(
                ValidationDiagnostic(
                    STATUS_NONFINITE_SAMPLE,
                    "sample row contains NaN or Infinity",
                    f"{base_path}.samples[{sample_index}]",
                    name,
                )
            )
            continue
        parsed_rows.append([float(value) for value in row])

    if len(parsed_rows) < 2:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_INSUFFICIENT_SAMPLES,
                "measurement must contain at least two valid samples",
                f"{base_path}.samples",
                name,
            )
        )
        return

    for previous, current, sample_index in zip(parsed_rows, parsed_rows[1:], range(1, len(parsed_rows))):
        if current[0] <= previous[0]:
            diagnostics.append(
                ValidationDiagnostic(
                    STATUS_NONMONOTONIC_TIME,
                    "sample timestamps must be strictly increasing",
                    f"{base_path}.samples[{sample_index}].time",
                    name,
                )
            )
            break

    if _all_accel_channels_constant(parsed_rows):
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_CONSTANT_SIGNAL,
                "all accelerometer channels are constant",
                f"{base_path}.samples",
                name,
            )
        )

    sample_rate = measurement.get("sample_rate_hz")
    if sample_rate is None:
        sample_rate = _derive_sample_rate_from_rows(parsed_rows)
    if sample_rate is None or not _is_finite(sample_rate) or float(sample_rate) <= 0:
        diagnostics.append(
            ValidationDiagnostic(
                STATUS_SAMPLE_RATE_OUT_OF_RANGE,
                "sample_rate_hz must be present or derivable from timestamps",
                f"{base_path}.sample_rate_hz",
                name,
            )
        )


def _sample_row(sample: Any) -> List[Any]:
    if isinstance(sample, Mapping):
        return [sample.get(column) for column in REQUIRED_SAMPLE_COLUMNS]
    try:
        return list(sample)
    except TypeError:
        return []


def _sample_time(sample: Any) -> float:
    row = _sample_row(sample)
    return float(row[0])


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _derive_sample_rate_from_rows(rows: Sequence[Sequence[float]]) -> Optional[float]:
    if len(rows) < 2:
        return None
    duration = rows[-1][0] - rows[0][0]
    if duration <= 0:
        return None
    return (len(rows) - 1) / duration


def _all_accel_channels_constant(rows: Sequence[Sequence[float]]) -> bool:
    return all(len({row[column_index] for row in rows}) == 1 for column_index in (1, 2, 3))


def _find_forbidden_fields(value: Any, path: str, forbidden: Iterable[str]) -> Iterable[str]:
    forbidden_set = set(forbidden)
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in forbidden_set:
                yield child_path
            yield from _find_forbidden_fields(child, child_path, forbidden_set)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            yield from _find_forbidden_fields(child, f"{path}[{index}]", forbidden_set)


def _marks_z_calibration(root: Mapping[str, Any], measurement: Mapping[str, Any]) -> bool:
    candidates = [measurement.get("axis"), measurement.get("calibration_axis")]
    metadata = root.get("metadata", {})
    if isinstance(metadata, Mapping):
        candidates.extend(
            [
                metadata.get("calibration_axis"),
                metadata.get("target_axis"),
                metadata.get("calibration_axes"),
                metadata.get("target_axes"),
            ]
        )
    measurement_metadata = measurement.get("metadata", {})
    if isinstance(measurement_metadata, Mapping):
        candidates.extend(
            [
                measurement_metadata.get("calibration_axis"),
                measurement_metadata.get("target_axis"),
                measurement_metadata.get("calibration_axes"),
                measurement_metadata.get("target_axes"),
            ]
        )
    return any(_contains_z(value) for value in candidates)


def _contains_z(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() == "z"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_z(item) for item in value)
    return False
