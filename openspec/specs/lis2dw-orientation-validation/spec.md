# lis2dw-orientation-validation Specification

## Purpose
LIS2DW orientation validation checks Max 4 X/Y toolhead accelerometer response, preserves configured axes-map metadata, and rejects bed-driven Z validation.

## Requirements

### Requirement: X/Y Orientation Validation
The system SHALL validate Max 4 toolhead LIS2DW orientation using X and Y toolhead movement only.

#### Scenario: X response is measured
- **WHEN** orientation validation runs and an X move produces sufficient accelerometer response
- **THEN** the result records the dominant accelerometer channel, polarity hint, dominance ratio, noise metric, and sample-rate estimate for X

#### Scenario: Y response is measured
- **WHEN** orientation validation runs and a Y move produces sufficient accelerometer response
- **THEN** the result records the dominant accelerometer channel, polarity hint, dominance ratio, noise metric, and sample-rate estimate for Y

### Requirement: Configured Axes Map Preservation
The system SHALL preserve the configured LIS2DW axes map in validation output and capture metadata.

#### Scenario: Axes map is configured
- **WHEN** `[lis2dw] axes_map` is present in Max 4 config
- **THEN** validation output and capture metadata include the configured axes map value

#### Scenario: Observation mismatches config
- **WHEN** observed X/Y dominant channels conflict with configured axes-map expectations
- **THEN** validation output records a mismatch diagnostic and does not edit configuration

### Requirement: Z Validation Exclusion
The system SHALL NOT validate toolhead accelerometer orientation from Max 4 bed Z movement.

#### Scenario: Z validation is requested
- **WHEN** orientation validation receives a Z-axis validation request
- **THEN** the request fails before motion and reports that Max 4 Z movement is unsupported for toolhead accelerometer validation

#### Scenario: Validation output is produced
- **WHEN** X/Y orientation validation completes
- **THEN** the output does not claim a measured Z-axis toolhead response

### Requirement: Signal Quality Diagnostics
The system SHALL report explicit diagnostics for ambiguous or unusable LIS2DW orientation data.

#### Scenario: Signal is ambiguous
- **WHEN** two or more accelerometer channels have similar response dominance for a commanded X or Y move
- **THEN** validation returns `ambiguous` for that axis with dominance metrics

#### Scenario: Signal is insufficient
- **WHEN** a commanded X or Y move produces no useful accelerometer response above noise threshold
- **THEN** validation returns `insufficient_signal` for that axis

#### Scenario: Signal is noisy
- **WHEN** noise metrics exceed the configured warning threshold
- **THEN** validation returns `noisy` with the observed metric

### Requirement: Preflight and Capture Integration
The system SHALL include orientation validation summaries where relevant.

#### Scenario: Preflight includes validation summary
- **WHEN** orientation validation has been run or is requested as part of preflight
- **THEN** preflight output includes configured axes map, X/Y validation status, and diagnostics

#### Scenario: Capture metadata includes validation summary
- **WHEN** a capture artifact is written after orientation validation data is available
- **THEN** metadata includes configured axes map and the latest X/Y orientation validation summary
