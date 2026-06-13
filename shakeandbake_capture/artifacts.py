from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from .models import (
    STATUS_INVALID_JSON,
    STATUS_IO_ERROR,
    CaptureArtifact,
    ReadResult,
    ValidationDiagnostic,
    ValidationResult,
    WriteResult,
)
from .validation import validate_capture_artifact


def read_capture_artifact(path: str | os.PathLike[str]) -> ReadResult:
    artifact_path = Path(path)
    try:
        with artifact_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except json.JSONDecodeError as exc:
        return ReadResult(
            artifact=None,
            path=str(artifact_path),
            validation=ValidationResult(
                STATUS_INVALID_JSON,
                (
                    ValidationDiagnostic(
                        STATUS_INVALID_JSON,
                        str(exc),
                        "$",
                    ),
                ),
            ),
        )
    except OSError as exc:
        return ReadResult(
            artifact=None,
            path=str(artifact_path),
            validation=ValidationResult(
                STATUS_IO_ERROR,
                (
                    ValidationDiagnostic(
                        STATUS_IO_ERROR,
                        str(exc),
                        str(artifact_path),
                    ),
                ),
            ),
        )

    try:
        artifact = CaptureArtifact.from_dict(raw)
    except (TypeError, ValueError, KeyError) as exc:
        return ReadResult(
            artifact=None,
            path=str(artifact_path),
            validation=ValidationResult(
                STATUS_INVALID_JSON,
                (
                    ValidationDiagnostic(
                        STATUS_INVALID_JSON,
                        f"invalid capture artifact shape: {exc}",
                        "$",
                    ),
                ),
            ),
        )

    return ReadResult(
        artifact=artifact,
        path=str(artifact_path),
        validation=validate_capture_artifact(raw),
    )


def write_capture_artifact(
    path: str | os.PathLike[str],
    artifact: CaptureArtifact | Mapping[str, Any],
    *,
    emit_metadata_sidecar: bool = False,
    metadata_sidecar_path: Optional[str | os.PathLike[str]] = None,
) -> WriteResult:
    capture = artifact if isinstance(artifact, CaptureArtifact) else CaptureArtifact.from_dict(artifact)
    validation = validate_capture_artifact(capture)
    if not validation.valid:
        return WriteResult(path=str(path), validation=validation)

    final_path = Path(path)
    _atomic_write_json(final_path, capture.to_dict())

    sidecar_path: Optional[Path] = None
    if emit_metadata_sidecar or metadata_sidecar_path is not None:
        sidecar_path = Path(metadata_sidecar_path) if metadata_sidecar_path is not None else final_path.with_suffix(
            final_path.suffix + ".metadata.json"
        )
        _atomic_write_json(
            sidecar_path,
            {
                "schema_version": capture.schema_version,
                "tool": capture.tool,
                "printer_model": capture.printer_model,
                "created_at": capture.created_at,
                "command": capture.command,
                "parameters": capture.parameters,
                "metadata": capture.metadata,
                "measurements": [
                    {
                        "name": measurement.name,
                        "axis": measurement.axis,
                        "sensor": measurement.sensor,
                        "sample_count": measurement.effective_sample_count,
                        "sample_rate_hz": measurement.sample_rate_hz,
                        "metadata": measurement.metadata,
                    }
                    for measurement in capture.measurements
                ],
            },
        )

    return WriteResult(
        path=str(final_path),
        validation=validation,
        metadata_sidecar_path=str(sidecar_path) if sidecar_path is not None else None,
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
