## ADDED Requirements

### Requirement: Speed Profile Capture Command
The system SHALL provide `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE` for Max 4 CoreXY speed-profile data acquisition.

#### Scenario: Command is registered
- **WHEN** the Shake&Bake Klipper extra is loaded
- **THEN** `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE` is available as a gcode command

### Requirement: CoreXY Direction Set
The system SHALL capture speed-profile data in the Max 4 CoreXY main directions.

#### Scenario: Direction measurements are created
- **WHEN** speed-profile acquisition runs
- **THEN** measurement blocks are created for 45 degree and 135 degree directions

### Requirement: Speed Grid Validation
The system SHALL validate speed-profile parameters before motion.

#### Scenario: Valid speed grid is accepted
- **WHEN** `MAX_SPEED` and `SPEED_INCREMENT` produce a bounded positive speed grid within configured printer limits
- **THEN** the command reports the planned measurement count and proceeds to preflight

#### Scenario: Invalid speed grid is rejected
- **WHEN** `MAX_SPEED` or `SPEED_INCREMENT` is nonpositive, exceeds configured limits, or produces too many measurements
- **THEN** the command fails before motion with a parameter validation error

### Requirement: Unsafe State Refusal
The system SHALL refuse speed-profile acquisition when preflight returns blocking findings.

#### Scenario: Preflight blocks acquisition
- **WHEN** the printer is printing, paused, homing, running virtual-SD work, not ready, missing accelerometer access, or has an out-of-bounds planned envelope
- **THEN** no speed-profile acquisition motion starts and the command reports blocking findings

### Requirement: Speed Profile Artifact
The system SHALL write one versioned raw capture artifact for successful speed-profile acquisition.

#### Scenario: Artifact contains speed and direction metadata
- **WHEN** speed-profile acquisition succeeds
- **THEN** every measurement block records direction angle, direction vector, speed, segment planning metadata, command parameters, probe point, accelerometer identity, axes map, preflight warnings, and state snapshots

### Requirement: Acquisition State Restoration
The system SHALL restore input-shaper and velocity-limit state after speed-profile acquisition attempts.

#### Scenario: Successful acquisition restores state
- **WHEN** speed-profile acquisition completes successfully
- **THEN** input-shaper state and velocity-limit state match the pre-acquisition snapshot

#### Scenario: Failed acquisition restores state
- **WHEN** motion, sampling, writing, or command parsing fails after temporary state changes
- **THEN** cleanup restores input-shaper state and velocity-limit state before command exit

### Requirement: Printer-Side Analysis Exclusion
The system SHALL NOT compute speed-profile analysis inside Klipper.

#### Scenario: Command completes
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE` finishes
- **THEN** output contains capture status and artifact path, and does not contain heatmaps, avoid bands, preferred speed ranges, angle-energy summaries, graphs, or slicer recommendations

### Requirement: Z-Axis Profile Exclusion
The system SHALL NOT acquire Z-axis speed-profile measurements for Max 4.

#### Scenario: Z profiling is requested
- **WHEN** a command parameter requests Z-axis speed-profile behavior
- **THEN** the command fails before motion and reports that Max 4 speed-profile acquisition supports X/Y CoreXY directions only
