# external-shaper-analysis Specification

## Purpose
External shaper analysis reads Shake&Bake raw X/Y captures outside Klipper and writes derived frequency evidence, diagnostics, summaries, and graphs without contacting the printer or editing configuration.

## Requirements

### Requirement: External Shaper CLI
The system SHALL provide an external CLI command that analyzes Shake&Bake X/Y shaper capture artifacts outside Klipper.

#### Scenario: Analyze command runs on a valid capture
- **WHEN** `shakeandbake analyze shaper <capture-file> --output-dir <dir>` is run with a valid X/Y capture artifact
- **THEN** the command writes shaper analysis outputs under the selected output directory

#### Scenario: Analyze command does not contact printer
- **WHEN** the external shaper analyzer runs
- **THEN** it does not issue Klipper commands, connect to the printer, or modify printer configuration

### Requirement: Capture Validation Gate
The system SHALL validate capture data before numerical analysis.

#### Scenario: Invalid capture blocks analysis
- **WHEN** the capture library returns unsupported schema, missing required metadata, nonmonotonic time, nonfinite sample, insufficient samples, or constant signal
- **THEN** the analyzer writes diagnostics and does not compute shaper recommendations

#### Scenario: Missing X/Y measurement blocks block recommendations
- **WHEN** a capture contains no valid X or Y measurement block
- **THEN** the analyzer writes diagnostics and does not write a proposed input-shaper config snippet

### Requirement: Z-Axis Analysis Exclusion
The system SHALL NOT process Max 4 Z-axis motion as shaper-analysis input.

#### Scenario: Capture contains Z-labeled measurement
- **WHEN** a capture artifact contains a Z-labeled measurement block
- **THEN** the shaper analyzer ignores it and records a diagnostic that Max 4 shaper analysis supports X and Y only

### Requirement: PSD Computation
The system SHALL compute PSD summaries for valid X/Y measurements.

#### Scenario: PSD is computed for a valid axis
- **WHEN** a valid X or Y measurement has monotonic timestamps, finite samples, and sufficient duration
- **THEN** the analyzer computes frequency bins, PSD values, sample-rate estimate, frequency resolution, and peak summary for that axis

#### Scenario: Degenerate PSD is rejected
- **WHEN** PSD values are empty, constant, all zero, or non-finite
- **THEN** the analyzer records an invalid PSD diagnostic and does not produce a recommendation for that axis

### Requirement: Frequency Evidence Reporting
The system SHALL report detected resonance-frequency evidence independently from shaper recommendation confidence.

#### Scenario: Peaks are detected
- **WHEN** PSD analysis finds local maxima above the configured thresholds
- **THEN** analysis JSON and the human-readable summary include the highest detected peak frequencies for each axis

#### Scenario: Graphs are generated
- **WHEN** graph output is enabled and an axis has PSD data
- **THEN** the analyzer writes SVG graphs with frequency axes, dB-scaled response, gridlines, and labeled detected peak frequencies

### Requirement: Shaper Candidate Evaluation
The system SHALL evaluate input-shaper candidates for valid X/Y PSD data.

#### Scenario: Candidate metrics are finite
- **WHEN** an axis has valid PSD data and candidate calculations produce finite residual vibration, smoothing, and acceleration estimates
- **THEN** the analyzer records candidate metrics for `zv`, `mzv`, `ei`, `2hump_ei`, and `3hump_ei`

#### Scenario: Recommendation is produced
- **WHEN** at least one candidate satisfies configured residual-vibration and smoothing constraints for an axis
- **THEN** the analyzer records a selected shaper type, frequency, residual vibration estimate, smoothing estimate, and acceleration guidance for that axis

#### Scenario: Recommendation is withheld
- **WHEN** no candidate satisfies configured constraints or metrics are invalid
- **THEN** the analyzer records a diagnostic and omits a recommendation for that axis

#### Scenario: Recommendation limits are explicit
- **WHEN** the analyzer emits a proposed input-shaper config snippet
- **THEN** the summary and JSON preserve the detected peak evidence so operators can compare the output against printer-side calibration results before applying changes

### Requirement: Damping Estimate
The system SHALL estimate resonance damping from PSD data using half-power bandwidth where valid.

#### Scenario: Half-power crossings exist
- **WHEN** the dominant PSD peak has valid lower and upper half-power crossings at `peak / 2`
- **THEN** the analyzer records damping ratio for that axis

#### Scenario: Half-power crossings are unavailable
- **WHEN** valid half-power crossings cannot be found
- **THEN** the analyzer records damping as unavailable with a diagnostic reason

### Requirement: Derived Output Files
The system SHALL write derived outputs separately from the raw capture artifact.

#### Scenario: Analysis succeeds
- **WHEN** X or Y analysis succeeds
- **THEN** the analyzer writes `analysis-shaper.json`, a human-readable summary, graph image files, and `input-shaper.proposed.cfg` when recommendations are valid

#### Scenario: Analysis output references capture
- **WHEN** any derived output is written
- **THEN** it references the source capture artifact path or fingerprint

### Requirement: LIS2DW Signal Warnings
The system SHALL report LIS2DW-specific signal-quality warnings when supported by capture data.

#### Scenario: Sample rate is estimated
- **WHEN** a valid measurement has timestamp data
- **THEN** the analyzer records estimated sample rate and frequency resolution in analysis output

#### Scenario: Aliasing or noisy signal is detected
- **WHEN** available sample-rate, PSD, or signal metrics indicate aliasing risk or excessive noise
- **THEN** the analyzer records a warning and includes it in JSON and human-readable outputs
