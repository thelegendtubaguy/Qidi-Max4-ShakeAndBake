## Context

Shake&Bake separates Max 4 data acquisition from external analysis. The Klipper process writes raw accelerometer captures; offline commands read those captures and produce derived outputs. The capture artifact is the shared contract between printer-side commands, tests, and external analyzers.

The artifact must not depend on external GPL implementation file formats, helper implementations, plot layout, command text, or compressed data schema. The artifact must not require NumPy, SciPy, Matplotlib, zstandard, Klipper internals, or printer access to read or validate metadata.

Max 4 capture context includes CoreXY X/Y motion, stock toolhead LIS2DW accelerometer, `[resonance_tester]` probe point, QIDI firmware/config fingerprints, input-shaper state, velocity-limit state, and fan/heater/chamber state. Z-axis movement is not represented as a calibration target because the Max 4 Z axis is bed-driven and the toolhead accelerometer does not measure bed Z movement.

## Goals / Non-Goals

**Goals:**

- Define a versioned raw capture artifact with explicit metadata and sample blocks.
- Provide a pure-Python library that writes, reads, and validates capture artifacts without heavy dependencies.
- Preserve raw samples separately from analysis summaries, plots, and proposed configuration snippets.
- Return explicit validation diagnostics instead of `NaN`, uncaught numeric exceptions, or silent acceptance of unusable captures.
- Keep the schema sensor-aware so each sample block identifies its accelerometer source.

**Non-Goals:**

- No Klipper command registration or printer motion.
- No PSD, spectrogram, shaper, belt, or speed-profile analysis.
- No plotting or report generation.
- No automatic writes to `printer.cfg`.
- No Z-axis calibration artifact semantics.

## Decisions

### Artifact container

Use a single capture file with a JSON header and chunked sample blocks, plus optional sidecar metadata JSON when the writer is configured to emit it. The canonical machine-readable content is the capture file; the sidecar mirrors metadata for simple inspection and test fixtures.

Alternative considered: plain CSV with comments. CSV is easy to inspect but weak for multi-measurement runs, typed metadata, sensor identity, validation diagnostics, and binary-safe chunking.

### Schema versioning

Use an integer `schema_version` at the artifact root and reject unsupported versions with a typed validation result. Readers must preserve unknown metadata fields when round-tripping artifacts.

Alternative considered: semantic-version strings. Integer schema versions are simpler for compatibility gates in the lightweight capture library.

### Sample representation

Represent each sample as time plus three accelerometer channels: `time`, `accel_x`, `accel_y`, `accel_z`. Store units in metadata and default to seconds plus meters-per-second-squared. Each measurement block carries `name`, `axis`, `sensor`, `sample_count`, and sample-rate estimate fields.

Alternative considered: opaque arrays without named columns. Named columns make validators and fixture tests simpler and reduce analyzer assumptions.

### Validation result model

Return structured validation statuses such as `valid`, `unsupported_schema`, `missing_required_field`, `invalid_sample_shape`, `insufficient_samples`, `nonmonotonic_time`, `nonfinite_sample`, `constant_signal`, and `sample_rate_out_of_range`. Validation must include the affected field or measurement name where available.

Alternative considered: raising exceptions for all invalid content. Typed diagnostics make CLI output, tests, and analyzer refusal behavior deterministic.

### Raw and derived separation

Capture files store acquisition metadata and raw samples only. Analysis outputs are separate JSON, graph, report, and config-snippet files that refer to a capture file and capture fingerprint.

Alternative considered: embedding analysis output in the raw capture. Embedded derived output makes reproducibility weaker because analysis algorithms and dependencies change independently from captured data.

## Risks / Trade-offs

- [Risk] Large text sample arrays can produce bulky captures → Mitigation: support chunked binary blocks behind the library interface while keeping metadata JSON-readable.
- [Risk] External analyzers may receive captures from unsupported schema versions → Mitigation: fail with `unsupported_schema` and include the observed version.
- [Risk] LIS2DW captures can contain aliasing and noisy low-amplitude signals → Mitigation: preserve sample-rate estimate, sensor name, axes map, and validation warnings for analyzer decisions.
- [Risk] Writer interruptions can leave partial files → Mitigation: write to a temporary path, flush, and atomically rename to the final capture path.
