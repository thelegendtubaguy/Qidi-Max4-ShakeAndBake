# belt-path-data-acquisition Specification

## Purpose
Max 4 printer-side Shake&Bake commands perform safe raw CoreXY belt-path accelerometer acquisition while keeping belt comparison analysis outside Klipper.

## Requirements

### Requirement: Belt Capture Command
The system SHALL provide `SHAKEANDBAKE_CAPTURE_BELTS` for Max 4 CoreXY belt-path data acquisition.

#### Scenario: Command is registered
- **WHEN** the Shake&Bake Klipper extra is loaded
- **THEN** `SHAKEANDBAKE_CAPTURE_BELTS` is available as a gcode command

### Requirement: CoreXY Belt Directions
The system SHALL capture A and B CoreXY belt-path directions with explicit vectors.

#### Scenario: A path is captured
- **WHEN** belt-path acquisition runs
- **THEN** one measurement block records path `A` with direction vector `(1, -1, 0)`

#### Scenario: B path is captured
- **WHEN** belt-path acquisition runs
- **THEN** one measurement block records path `B` with direction vector `(1, 1, 0)`

### Requirement: Matched Sweep Parameters
The system SHALL use matched resonance sweep parameters for A and B path measurements.

#### Scenario: Parameters are applied to both paths
- **WHEN** `FREQ_START`, `FREQ_END`, `HZ_PER_SEC`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, or `ACCEL_CHIP` is provided
- **THEN** both A and B measurement blocks record the same parameter values

#### Scenario: Default belt sweep range matches Max 4 calibration range
- **WHEN** `SHAKEANDBAKE_CAPTURE_BELTS` runs without `FREQ_END`
- **THEN** both A and B captures use a default sweep ending at `133 Hz`

### Requirement: Max 4 Internal Accelerometer Capture
The system SHALL support QIDI Max 4 internal accelerometer sampling APIs for belt-path acquisition.

#### Scenario: Internal client sampling is available
- **WHEN** the LIS2DW object exposes `start_internal_client` and the resonance tester exposes `test.prepare_test` and `test.run_test`
- **THEN** belt-path capture starts an internal accelerometer client before A/B motion and finishes measurements before reading samples

#### Scenario: Direct sample acquisition is available
- **WHEN** the accelerometer object exposes direct `acquire_samples` or `read_samples`
- **THEN** belt-path capture uses that method to read samples after A/B motion

### Requirement: Unsafe State Refusal
The system SHALL refuse belt-path acquisition when preflight returns blocking findings.

#### Scenario: Preflight blocks acquisition
- **WHEN** the printer is printing, paused, homing, running virtual-SD work, not ready, missing accelerometer access, or has an out-of-bounds planned envelope
- **THEN** no belt-path acquisition motion starts and the command reports blocking findings

### Requirement: Acquisition State Restoration
The system SHALL restore input-shaper and velocity-limit state after belt-path acquisition attempts.

#### Scenario: Successful acquisition restores state
- **WHEN** A and B capture complete successfully
- **THEN** input-shaper state and velocity-limit state match the pre-acquisition snapshot

#### Scenario: Failed acquisition restores state
- **WHEN** motion, sampling, writing, or command parsing fails after temporary state changes
- **THEN** cleanup restores input-shaper state and velocity-limit state before command exit

### Requirement: Belt Capture Artifact
The system SHALL write one versioned raw capture artifact for a successful belt-path acquisition.

#### Scenario: Artifact contains paired measurements
- **WHEN** `SHAKEANDBAKE_CAPTURE_BELTS` succeeds
- **THEN** the capture artifact contains A and B measurement blocks, command parameters, planned motion envelope, probe point, accelerometer identity, axes map, preflight warnings, and state snapshots

### Requirement: Printer-Side Analysis Exclusion
The system SHALL NOT compute belt comparison results inside Klipper.

#### Scenario: Command completes
- **WHEN** `SHAKEANDBAKE_CAPTURE_BELTS` finishes
- **THEN** output contains capture status and artifact path, and does not contain PSD comparison, similarity percentage, peak-pairing result, graph path, or mechanical-health label
