# printer-data-acquisition Specification

## Purpose
Max 4 printer-side Shake&Bake commands perform safe preflight checks and raw X/Y accelerometer acquisition while keeping analysis outside Klipper.

## Requirements

### Requirement: Klipper Command Registration
The system SHALL register explicit Shake&Bake data-acquisition commands in Klipper.

#### Scenario: Plugin loads
- **WHEN** the `shakeandbake` Klipper extra is loaded
- **THEN** `SHAKEANDBAKE_PREFLIGHT`, `SHAKEANDBAKE_CAPTURE_SHAPER`, `SHAKEANDBAKE_CAPTURE_BELTS`, and `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` are registered gcode commands

#### Scenario: Removed diagnostic commands are absent
- **WHEN** the `shakeandbake` Klipper extra is loaded
- **THEN** no static-frequency excitation command is registered

#### Scenario: Heavy packages are absent from plugin imports
- **WHEN** the Klipper plugin module is imported
- **THEN** it does not import NumPy, SciPy, Matplotlib, plotting modules, or the external analyzer package

### Requirement: Preflight Command
The system SHALL expose preflight results through `SHAKEANDBAKE_PREFLIGHT`.

#### Scenario: Preflight reports ready state
- **WHEN** `SHAKEANDBAKE_PREFLIGHT` runs on a ready and idle Max 4 with valid X/Y acquisition configuration
- **THEN** the command reports ready status, supported axes X/Y, probe point, accelerometer identity, and warnings from the preflight result

#### Scenario: Preflight reports blocking state
- **WHEN** `SHAKEANDBAKE_PREFLIGHT` runs while the printer is printing, paused, homing, running virtual-SD work, not ready, missing accelerometer access, or has an out-of-bounds planned envelope
- **THEN** the command reports not-ready status and the blocking finding codes

### Requirement: X/Y Shaper Capture Command
The system SHALL capture raw accelerometer data for X and Y shaper analysis through `SHAKEANDBAKE_CAPTURE_SHAPER`.

#### Scenario: Capture all axes
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER AXIS=ALL` runs after successful preflight
- **THEN** the command records X and Y measurement blocks and writes one versioned capture artifact

#### Scenario: Capture one axis
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER AXIS=X` or `AXIS=Y` runs after successful preflight
- **THEN** the command records only the requested X or Y measurement block and writes one versioned capture artifact

#### Scenario: Default shaper sweep range matches Max 4 calibration range
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER` runs without `FREQ_END`
- **THEN** the capture uses a default sweep ending at `133 Hz`

#### Scenario: Capture output path is reported
- **WHEN** capture artifact writing succeeds
- **THEN** the command reports the capture artifact path and measurement names

### Requirement: Z-Axis Capture Rejection
The system SHALL reject Z-axis capture requests.

#### Scenario: Z axis is requested
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER AXIS=Z` is invoked
- **THEN** the command fails before motion and reports that Max 4 Shake&Bake acquisition supports X and Y only

### Requirement: Unsafe State Refusal
The system SHALL refuse acquisition before motion when preflight has blocking findings.

#### Scenario: Printer is not safe for acquisition
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER` runs and preflight returns any blocking finding
- **THEN** no acquisition motion starts, no input-shaper state is changed, and the blocking findings are reported

### Requirement: Acquisition State Restoration
The system SHALL restore input-shaper and velocity-limit state after acquisition attempts.

#### Scenario: Successful capture restores state
- **WHEN** acquisition completes successfully
- **THEN** input-shaper state and velocity-limit state match the pre-acquisition snapshot

#### Scenario: Failed capture restores state
- **WHEN** acquisition raises a motion, sampling, writing, or command error after temporary state changes
- **THEN** cleanup restores input-shaper state and velocity-limit state before the command exits

### Requirement: Capture Artifact Metadata
The system SHALL write acquisition context into the raw capture artifact.

#### Scenario: Capture metadata includes command context
- **WHEN** a shaper capture artifact is written
- **THEN** metadata includes command parameters, planned motion envelope, probe point, accelerometer identity, axes map, input-shaper pre-state, velocity-limit pre-state, fan/heater/chamber snapshot, and preflight warnings

### Requirement: Printer-Side Analysis Exclusion
The system SHALL NOT perform shaper analysis inside Klipper.

#### Scenario: Capture command completes
- **WHEN** `SHAKEANDBAKE_CAPTURE_SHAPER` finishes
- **THEN** command output contains capture status and artifact path, and does not contain shaper type recommendations, resonance plots, PSD summaries, or proposed `printer.cfg` edits
