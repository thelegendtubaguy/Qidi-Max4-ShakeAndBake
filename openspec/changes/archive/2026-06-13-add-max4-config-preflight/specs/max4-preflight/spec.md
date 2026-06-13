## ADDED Requirements

### Requirement: Max 4 Configuration Inspection
The system SHALL inspect QIDI Max 4 configuration values required for Shake&Bake X/Y data acquisition.

#### Scenario: Printer section is parsed
- **WHEN** a Max 4 config contains `[printer]`
- **THEN** preflight config inspection extracts kinematics, max velocity, max acceleration, max Z velocity, max Z acceleration, and square-corner velocity when present

#### Scenario: Resonance tester section is parsed
- **WHEN** a Max 4 config contains `[resonance_tester]`
- **THEN** preflight config inspection extracts accel chip, accel per Hz, max smoothing, and probe point values when present

#### Scenario: LIS2DW section is parsed
- **WHEN** a Max 4 config contains `[lis2dw]`
- **THEN** preflight config inspection extracts axes map and accelerometer identity fields when present

### Requirement: QIDI Closed-Loop Motor Metadata
The system SHALL parse QIDI `[closed_loop x]` and `[closed_loop y]` sections for X/Y motor metadata.

#### Scenario: Closed-loop current fields are present
- **WHEN** `[closed_loop x]` and `[closed_loop y]` contain current and microstep fields
- **THEN** preflight config inspection reports X/Y run current, hold current, home current, and microstep metadata

#### Scenario: Standard TMC sections are absent
- **WHEN** no standard X/Y TMC driver sections exist
- **THEN** preflight config inspection does not fail solely because `[tmc* stepper_x]` and `[tmc* stepper_y]` sections are absent

### Requirement: Preflight Readiness Result
The system SHALL return a structured preflight result with readiness, blocking findings, warnings, and state snapshots.

#### Scenario: Idle printer passes readiness checks
- **WHEN** the printer is ready, idle, homed as required, has accelerometer access, has acceptable host resources, and the planned X/Y envelope is within bounds
- **THEN** preflight returns ready with no blocking findings

#### Scenario: Active print blocks acquisition
- **WHEN** the printer is printing, paused, running virtual-SD work, homing, or not ready
- **THEN** preflight returns not ready with a blocking finding that names the active unsafe state

#### Scenario: Host resource warning is emitted
- **WHEN** host load, free memory, or free disk is below the configured warning threshold but not a known unsafe state
- **THEN** preflight returns a warning with the metric name and observed value

### Requirement: Planned Motion Envelope Validation
The system SHALL validate planned X/Y acquisition movement against Max 4 configured travel limits and probe point.

#### Scenario: Envelope is inside bounds
- **WHEN** the planned X/Y motion envelope plus margin is inside configured Max 4 bounds
- **THEN** preflight does not emit a motion-envelope blocking finding

#### Scenario: Envelope exceeds bounds
- **WHEN** the planned X/Y motion envelope exceeds configured bounds or margin
- **THEN** preflight returns not ready with a blocking `motion_envelope_out_of_bounds` finding

### Requirement: Z-Axis Acquisition Exclusion
The system SHALL exclude Z-axis acquisition and Z-axis resonance interpretation for Max 4 data acquisition.

#### Scenario: Z axis is requested
- **WHEN** preflight receives an acquisition request for Z-axis resonance or Z-axis shaper data
- **THEN** preflight returns not ready with a blocking finding that Z-axis acquisition is unsupported for Max 4

#### Scenario: Supported axes are reported
- **WHEN** preflight reports supported acquisition axes for Max 4
- **THEN** the supported axes are X and Y only

### Requirement: State Snapshot Capture
The system SHALL capture machine state needed for downstream capture metadata.

#### Scenario: State snapshot is available
- **WHEN** preflight runs before an acquisition command
- **THEN** the result includes input-shaper state, velocity-limit state, fan state, heater state, chamber state, probe point, accelerometer identity, and axes map when available
