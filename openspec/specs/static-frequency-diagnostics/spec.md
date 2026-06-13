# static-frequency-diagnostics Specification

## Purpose
Static-frequency diagnostics provide fixed-frequency Max 4 X/Y/A/B excitation with optional raw recording and external analysis for locating resonating components.

## Requirements

### Requirement: Static Excitation Command
The system SHALL provide `SHAKEANDBAKE_EXCITE` for fixed-frequency Max 4 diagnostics.

#### Scenario: Command is registered
- **WHEN** the Shake&Bake Klipper extra is loaded
- **THEN** `SHAKEANDBAKE_EXCITE` is available as a gcode command

### Requirement: Supported Excitation Axes
The system SHALL support X, Y, A, and B excitation axes only.

#### Scenario: X or Y is requested
- **WHEN** `SHAKEANDBAKE_EXCITE AXIS=X` or `AXIS=Y` is invoked with valid parameters
- **THEN** the command plans excitation in the requested toolhead axis direction

#### Scenario: A or B is requested
- **WHEN** `SHAKEANDBAKE_EXCITE AXIS=A` or `AXIS=B` is invoked with valid parameters
- **THEN** the command plans excitation using CoreXY direction `(1, -1, 0)` for A or `(1, 1, 0)` for B

#### Scenario: Z is requested
- **WHEN** `SHAKEANDBAKE_EXCITE AXIS=Z` is invoked
- **THEN** the command fails before motion and reports that Max 4 Shake&Bake excitation supports X, Y, A, and B only

### Requirement: Parameter Validation
The system SHALL validate fixed-frequency excitation parameters before motion.

#### Scenario: Valid parameters are accepted
- **WHEN** `FREQUENCY`, `DURATION`, and supported axis parameters are within configured limits
- **THEN** the command proceeds to preflight

#### Scenario: Invalid parameters are rejected
- **WHEN** frequency or duration is missing, nonpositive, or exceeds configured limits
- **THEN** the command fails before motion with a parameter validation error

### Requirement: Safe Excitation Lifecycle
The system SHALL run preflight and restore modified state around excitation.

#### Scenario: Preflight blocks excitation
- **WHEN** preflight returns blocking findings
- **THEN** no excitation motion starts and the command reports blocking findings

#### Scenario: Excitation restores state
- **WHEN** excitation succeeds or fails after temporary state changes
- **THEN** cleanup restores input-shaper and velocity-limit state before command exit

### Requirement: Optional Recording
The system SHALL optionally record accelerometer data during static-frequency excitation.

#### Scenario: Recording is enabled
- **WHEN** `SHAKEANDBAKE_EXCITE ... RECORD=1` completes sampling successfully
- **THEN** the command writes a versioned capture artifact with `tool: static-frequency`, axis label, direction vector, frequency, duration, samples, and state metadata

#### Scenario: Recording is disabled
- **WHEN** `SHAKEANDBAKE_EXCITE ... RECORD=0` completes
- **THEN** no capture artifact is written and command output reports excitation completion

### Requirement: External Static-Frequency Analysis
The system SHALL analyze recorded static-frequency captures outside Klipper.

#### Scenario: Static-frequency capture is analyzed
- **WHEN** `shakeandbake analyze static-frequency <capture-file> --output-dir <dir>` is run with a valid capture
- **THEN** the analyzer writes analysis JSON, human-readable summary, and graph files for spectrogram and cumulative energy over time when graph generation succeeds

#### Scenario: Invalid capture is diagnostic
- **WHEN** the capture has invalid metadata, invalid samples, unsupported axis, or unusable sample rate
- **THEN** the analyzer writes diagnostics and does not produce spectrogram metrics
