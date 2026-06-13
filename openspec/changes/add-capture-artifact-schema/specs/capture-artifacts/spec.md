## ADDED Requirements

### Requirement: Capture Artifact Schema
The system SHALL write Shake&Bake capture artifacts with `schema_version`, `tool`, `printer_model`, run metadata, measurement metadata, and raw accelerometer samples.

#### Scenario: Required root metadata is present
- **WHEN** a capture artifact is written for a Max 4 X/Y acquisition
- **THEN** the artifact contains `schema_version`, `tool`, `printer_model`, `created_at`, `command`, `parameters`, `measurements`, and `metadata`

#### Scenario: Printer model is explicit
- **WHEN** a capture artifact is written for a QIDI Max 4
- **THEN** `printer_model` is `qidi_max_4`

### Requirement: Measurement Sample Blocks
The system SHALL store each measurement as a named block with time and three accelerometer channels.

#### Scenario: Measurement samples use named columns
- **WHEN** a measurement block is read
- **THEN** each sample row is interpreted as `time`, `accel_x`, `accel_y`, and `accel_z`

#### Scenario: Measurement identifies sensor source
- **WHEN** a capture includes samples from the stock Max 4 accelerometer
- **THEN** the measurement metadata identifies the sensor as `lis2dw` or the configured accelerometer object name

### Requirement: Max 4 Acquisition Metadata
The system SHALL preserve Max 4 acquisition metadata needed to reproduce external analysis.

#### Scenario: Motion and printer state are captured
- **WHEN** a capture artifact is written
- **THEN** metadata includes the planned motion envelope, probe point, axes map at capture time, input-shaper state before capture, velocity-limit state before capture, and fan/heater/chamber state snapshot

#### Scenario: Firmware and config fingerprints are captured
- **WHEN** firmware or configuration fingerprints are available to the writer
- **THEN** metadata includes Klipper version, Klipper git hash, QIDI firmware fingerprint, and configuration fingerprint fields

### Requirement: No Z-Axis Calibration Semantics
The system SHALL NOT define Z-axis resonance calibration or Z-axis shaper analysis semantics in capture artifacts.

#### Scenario: Z movement is not a calibration target
- **WHEN** a Max 4 capture artifact is written
- **THEN** the artifact does not mark bed-driven Z motion as a valid toolhead resonance calibration axis

### Requirement: Capture Validation
The system SHALL validate capture artifacts before external analysis consumes them.

#### Scenario: Valid capture passes validation
- **WHEN** a capture has supported schema version, required metadata, monotonic timestamps, finite sample values, sufficient samples, and nonconstant signal
- **THEN** validation returns `valid`

#### Scenario: Nonmonotonic time is rejected
- **WHEN** a measurement contains duplicate or decreasing timestamps
- **THEN** validation returns `nonmonotonic_time` with the measurement name

#### Scenario: Non-finite samples are rejected
- **WHEN** a measurement contains `NaN`, `Infinity`, or `-Infinity`
- **THEN** validation returns `nonfinite_sample` with the measurement name

#### Scenario: Degenerate signal is rejected
- **WHEN** every accelerometer channel in a measurement is constant or empty
- **THEN** validation returns `constant_signal` or `insufficient_samples` with the measurement name

### Requirement: Raw and Derived Artifact Separation
The system SHALL keep raw capture artifacts separate from analysis outputs.

#### Scenario: Raw artifact contains no analysis result
- **WHEN** an analyzer creates summary JSON, graph files, reports, or proposed config snippets
- **THEN** those outputs are written as separate files that reference the raw capture artifact

### Requirement: Lightweight Capture Library
The system SHALL provide capture read/write/validate behavior without importing numerical, plotting, or Klipper packages.

#### Scenario: Capture library imports in a clean Python process
- **WHEN** the capture library is imported
- **THEN** it does not import NumPy, SciPy, Matplotlib, zstandard, or Klipper modules
