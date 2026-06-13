## Context

The Max 4 stock toolhead accelerometer is LIS2DW with configured axes map `y, z, -x` in stock configs. Shake&Bake captures should preserve the configured axes map and can validate that X/Y toolhead moves produce plausible accelerometer response. The bed-driven Z axis does not move the toolhead accelerometer, so Z movement is not a valid orientation signal.

Orientation validation is a safety and diagnostics feature. It does not edit configuration. It reports observed X/Y dominance, polarity hints, noise, sample-rate estimate, and ambiguity diagnostics.

## Goals / Non-Goals

**Goals:**

- Validate LIS2DW availability and X/Y dynamic response using bounded X/Y moves.
- Compare observed X/Y response against configured axes map where possible.
- Report confidence, dominant accelerometer channels, polarity hints, noise metrics, and sample-rate estimate.
- Record validation results in preflight output and capture metadata.
- Reject Z-axis validation requests.

**Non-Goals:**

- No full three-axis axes-map calibration.
- No use of bed Z movement as a toolhead accelerometer signal.
- No automatic config edits.
- No shaper, belt, or speed-profile analysis.

## Decisions

### X/Y-only validation

Run short, bounded X and Y toolhead moves and examine accelerometer response after DC/gravity offset removal. Determine dominant accelerometer channel and polarity hint per commanded axis. Mark Z as unsupported rather than inferred.

Alternative considered: move Z and infer a third axis. Bed-driven Z does not move the toolhead accelerometer and would produce misleading results.

### Confidence model

Report dominance ratio, noise floor, sample-rate estimate, and ambiguity flags. A result can be `valid`, `ambiguous`, `insufficient_signal`, `noisy`, or `unavailable`.

Alternative considered: produce a single pass/fail result. Diagnostics are more useful for LIS2DW noise and configuration issues.

### Config handling

Compare observations with configured `axes_map` and report mismatches. Do not write corrected axes-map values. Suggested config text may be reported only as diagnostic text outside automatic mutation.

Alternative considered: update config automatically. Orientation mistakes should be reviewed by an operator before config changes.

### Metadata reuse

Capture artifacts include configured axes map and latest orientation validation summary when available. External analyzers can use the metadata for warnings and axis interpretation.

Alternative considered: analyzer re-validates orientation from every capture. Acquisition captures are not always designed to isolate orientation response.

## Risks / Trade-offs

- [Risk] Short X/Y moves may be noisy or affected by structural ringing → Mitigation: remove DC offset, low-pass or smooth only for validation metrics, and return ambiguity diagnostics.
- [Risk] Missing Z validation leaves one configured channel unchecked → Mitigation: state that Max 4 Z movement is unsupported for toolhead accelerometer validation and preserve configured axes map as metadata.
- [Risk] Polarity hints can be wrong with poor signal → Mitigation: require dominance and signal thresholds before reporting a confident result.
