## ADDED Requirements

### Requirement: Max 4 Speed-Limit Capture Command
The system SHALL register `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` as the single printer-side command for Max 4 speed-limit evidence acquisition.

#### Scenario: Command is registered
- **WHEN** the Shake&Bake Klipper extra loads successfully
- **THEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` is registered as a gcode command with an explicit description

#### Scenario: Heavy analysis packages are absent from command imports
- **WHEN** the Klipper plugin module is imported
- **THEN** it does not import NumPy, SciPy, Matplotlib, plotting modules, or external analyzer modules

#### Scenario: Capture command reports artifact path
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` finishes writing a valid raw artifact
- **THEN** the command reports the artifact path, completed phase names, and candidate count

### Requirement: Single-Command Evidence Run
The system SHALL use `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` to collect the raw evidence needed for external speed-limit recommendations in one artifact.

#### Scenario: Default run includes all recommendation evidence phases
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` runs with default phase settings after successful preflight
- **THEN** the planned run includes X/Y endstop baseline scans, coupled velocity/acceleration stress candidates, X/Y shaper sweeps, and speed/direction vibration measurements

#### Scenario: One artifact contains all completed phases
- **WHEN** the default speed-limit capture completes
- **THEN** one raw `.sbcapture.json` artifact contains metadata and measurement blocks for every completed speed-limit evidence phase

#### Scenario: Raw capture contains no recommendations
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` completes
- **THEN** command output and raw artifact content do not contain final `max_velocity`, `max_accel`, slicer speed recommendations, graphs, or proposed config snippets

### Requirement: Max 4 Scope and Z-Axis Exclusion
The system SHALL restrict speed-limit evidence acquisition to QIDI Max 4 CoreXY X/Y motion.

#### Scenario: Non-CoreXY kinematics are rejected
- **WHEN** the parsed Max 4 configuration reports kinematics other than `corexy`
- **THEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` fails before motion with a blocking kinematics diagnostic

#### Scenario: Z-axis parameters are rejected
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` receives an axis or direction parameter requesting Z-axis speed, acceleration, resonance, or missed-step testing
- **THEN** the command fails before motion and reports that Max 4 speed-limit evidence supports X/Y CoreXY motion only

#### Scenario: Standard X/Y TMC sections are not required
- **WHEN** the Max 4 configuration has `[closed_loop x]` and `[closed_loop y]` metadata but no standard X/Y TMC driver sections
- **THEN** speed-limit evidence acquisition does not fail solely because standard X/Y TMC driver sections are absent

### Requirement: Safe Planning and Preflight
The system SHALL validate the complete speed-limit evidence run before starting acquisition motion.

#### Scenario: Unsafe printer state blocks capture
- **WHEN** the printer is printing, paused, running virtual-SD work, homing, not ready, missing accelerometer access, or in another blocking preflight state
- **THEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` starts no acquisition motion, changes no input-shaper or velocity-limit state, and reports the blocking finding codes

#### Scenario: Planned envelope is validated
- **WHEN** the speed-limit command builds its phase plan and candidate grid
- **THEN** preflight validates the complete planned X/Y envelope plus safety margin against configured Max 4 travel bounds before motion starts

#### Scenario: Candidate grid is bounded
- **WHEN** command parameters generate a velocity/acceleration candidate grid
- **THEN** the grid is rejected before motion if it exceeds the configured candidate-count limit, configured velocity limit, configured acceleration limit, or validated motion envelope

#### Scenario: Planned run is reported before motion
- **WHEN** preflight and planning succeed
- **THEN** the command reports phase names, candidate count, speed range, acceleration range, and safety thresholds before starting acquisition motion

### Requirement: State Restoration
The system SHALL restore temporary printer state after speed-limit evidence acquisition attempts.

#### Scenario: Successful run restores state
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` completes successfully
- **THEN** input-shaper state, velocity-limit state, square-corner velocity, and supported temporary motion settings match the pre-acquisition snapshot

#### Scenario: Failed run restores state
- **WHEN** `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` raises a command, planning, motion, sampling, endstop-scan, closed-loop, or write error after temporary state changes
- **THEN** cleanup restores input-shaper state, velocity-limit state, square-corner velocity, and supported temporary motion settings before the command exits

#### Scenario: Restoration warnings are preserved
- **WHEN** one or more restoration operations fail
- **THEN** the command reports restoration warnings and the raw artifact metadata includes restoration status when an artifact is written

### Requirement: Endstop Baseline Evidence
The system SHALL establish X and Y endstop-trigger baseline evidence before stress-motion candidates run.

#### Scenario: Baseline scans are recorded
- **WHEN** the speed-limit evidence run starts its baseline phase
- **THEN** the command records multiple low-speed X and Y endstop-trigger observations with axis, configured endstop side, commanded trigger coordinate, sample index, scan speed, timestamp, and trigger availability

#### Scenario: Baseline threshold is derived
- **WHEN** enough baseline trigger observations are available
- **THEN** the raw artifact records baseline spread and the safety threshold used for later trigger-drift checks

#### Scenario: Missing baseline blocks stress testing
- **WHEN** baseline trigger observations cannot be collected for X or Y
- **THEN** stress-motion candidates do not run and the artifact records a blocking baseline diagnostic if an artifact is written

### Requirement: Missed-Step Evidence from Trigger Drift
The system SHALL collect X/Y position-loss evidence after each stress-motion candidate using endstop-trigger drift against the baseline.

#### Scenario: Candidate trigger drift is recorded
- **WHEN** a stress-motion candidate completes
- **THEN** the command records post-candidate X and Y trigger observations, drift from baseline, drift threshold, and candidate identifier

#### Scenario: Excessive drift stops escalation
- **WHEN** post-candidate X or Y trigger drift exceeds the configured safety threshold
- **THEN** the command records the candidate as an unsafe escalation boundary, rehomes X/Y, and does not run higher-risk candidates in that candidate region

#### Scenario: Trigger scan failure stops escalation
- **WHEN** a required post-candidate trigger scan fails or returns an unavailable trigger observation
- **THEN** the command records the failure, rehomes X/Y when possible, and does not continue escalating motion limits

### Requirement: Coupled Velocity and Acceleration Candidates
The system SHALL test motion limits as coupled velocity/acceleration candidates.

#### Scenario: Candidate records include coupled parameters
- **WHEN** a stress-motion candidate is planned
- **THEN** the raw artifact records candidate id, requested velocity, requested acceleration, motion directions, repetitions, segment length, planner settings, and planned envelope

#### Scenario: X, Y, and CoreXY directions are represented
- **WHEN** the default candidate grid is built
- **THEN** candidates include Cartesian X motion, Cartesian Y motion, and CoreXY diagonal or motor-path stress directions needed to exercise both X/Y motors

#### Scenario: Independent maxima are not emitted by the printer
- **WHEN** the stress-motion phase completes
- **THEN** the raw artifact records candidate evidence without emitting independent printer-side `max_velocity` or `max_accel` recommendations

### Requirement: QIDI Closed-Loop Supplemental Evidence
The system SHALL record available QIDI X/Y closed-loop status and coder observations as supplemental speed-limit evidence.

#### Scenario: Closed-loop status is available
- **WHEN** X/Y closed-loop status or coder data is available before or after a baseline scan or stress candidate
- **THEN** the raw artifact records the raw field names, values, axis or motor labels, observation time, and associated phase or candidate id

#### Scenario: Explicit closed-loop fault stops escalation
- **WHEN** closed-loop status reports an explicit fault, alarm, motor position error, no-response state, or equivalent unsafe state
- **THEN** the command records the state, rehomes X/Y when possible, and does not continue escalating motion limits

#### Scenario: Closed-loop status is unavailable
- **WHEN** closed-loop status or coder data cannot be queried on a supported Max 4 configuration
- **THEN** speed-limit evidence acquisition can continue using endstop-trigger evidence and records a nonblocking closed-loop-unavailable diagnostic

### Requirement: Vibration Evidence in Speed-Limit Artifact
The system SHALL include vibration evidence needed to constrain print-quality recommendations in the same speed-limit capture artifact.

#### Scenario: X/Y shaper measurements are captured
- **WHEN** the default speed-limit evidence run reaches the shaper phase
- **THEN** the artifact includes X and Y resonance measurement blocks compatible with external shaper analysis

#### Scenario: Speed-profile grid is validated
- **WHEN** the speed-profile phase builds its speed grid from command parameters
- **THEN** the grid contains positive speeds through the requested maximum, uses a positive increment, stays within configured printer limits, and stays under the measurement-count limit before motion starts

#### Scenario: Speed-profile directions are defined
- **WHEN** the default speed-profile phase is planned
- **THEN** the planned measurements include Max 4 CoreXY 45 degree and 135 degree directions with direction angle and direction vector metadata

#### Scenario: Speed-profile measurements are captured
- **WHEN** the default speed-limit evidence run reaches the speed-profile phase
- **THEN** the artifact includes raw speed/direction vibration measurement blocks for Max 4 CoreXY 45 degree and 135 degree directions across the planned speed grid

#### Scenario: Speed-profile measurement metadata is complete
- **WHEN** a speed-profile measurement block is written
- **THEN** it records speed, direction angle, direction vector, segment planning metadata, acceleration, travel speed, size or segment length, accelerometer object, probe point, axes map, preflight warnings, and state snapshots needed for external analysis

#### Scenario: Vibration phase failure is explicit
- **WHEN** a shaper or speed-profile measurement phase fails after motion-limit evidence has been collected
- **THEN** the artifact records the failed phase diagnostic and preserves already-collected raw evidence when artifact writing is still possible

### Requirement: Speed-Limit Evidence Artifact Metadata
The system SHALL write speed-limit evidence in a versioned raw artifact with explicit phase, candidate, and safety metadata.

#### Scenario: Speed-limit metadata is present
- **WHEN** a speed-limit evidence artifact is written
- **THEN** metadata includes command parameters, phase plan, planned motion envelope, probe point, axes map, accelerometer identity, input-shaper pre-state, velocity-limit pre-state, square-corner velocity, fan/heater/chamber snapshot, host-resource warnings, and restoration status

#### Scenario: Candidate evidence is present
- **WHEN** stress-motion candidates run
- **THEN** metadata includes candidate records, trigger observations, trigger drift values, safety thresholds, closed-loop observations, and safety-stop reasons when present

#### Scenario: Planner settings are preserved
- **WHEN** candidate evidence is written
- **THEN** metadata includes planner settings that affect interpretation, including configured max velocity, configured max acceleration, square-corner velocity, and min-cruise-ratio-equivalent settings when available

### Requirement: External Speed-Limits Analyzer
The system SHALL provide `shakeandbake analyze speed-limits <capture> --output-dir <dir>` for external analysis of speed-limit evidence artifacts.

#### Scenario: Analyzer accepts valid speed-limit capture
- **WHEN** the analyzer receives a valid `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` artifact
- **THEN** it writes `analysis-speed-limits.json` and a human-readable summary under the requested output directory

#### Scenario: Analyzer options configure vibration analysis
- **WHEN** the analyzer command is invoked
- **THEN** it accepts options for output directory, frequency band, angular resolution, avoid-band thresholds, preferred-range thresholds, graph enablement, and summary-only behavior

#### Scenario: Analyzer does not contact printer
- **WHEN** speed-limit analysis runs
- **THEN** it does not issue Klipper commands, connect to the printer, modify slicer profiles, or modify printer configuration

#### Scenario: Analyzer rejects invalid capture
- **WHEN** the analyzer receives a capture with unsupported schema, missing speed-limit metadata, invalid candidate records, invalid trigger observations, or invalid measurement samples required for enabled phases
- **THEN** it exits with diagnostics and does not write final recommendations

#### Scenario: Derived outputs are separate
- **WHEN** the analyzer writes JSON, summaries, graphs, reports, or proposed config snippets
- **THEN** every derived output is separate from the raw capture and references the source capture fingerprint or path

### Requirement: Embedded Speed-Profile Analysis
The speed-limits analyzer SHALL analyze the embedded Max 4 CoreXY speed-profile measurements for vibration-energy guidance.

#### Scenario: Complete speed-profile grid is valid
- **WHEN** the capture contains valid 45 degree and 135 degree measurement blocks for each expected speed
- **THEN** the analyzer proceeds with PSD-energy analysis for those measurements

#### Scenario: Incomplete speed-profile grid is diagnostic
- **WHEN** a speed or required direction is missing
- **THEN** the analyzer records a diagnostic and marks affected projected speed-profile results unavailable

#### Scenario: Invalid speed-profile samples block affected measurements
- **WHEN** a speed-profile measurement has nonmonotonic time, non-finite samples, insufficient samples, constant signal, or unusable sample rate
- **THEN** the analyzer records measurement diagnostics and excludes that measurement from derived speed-profile metrics

#### Scenario: PSD energy is computed
- **WHEN** a speed-profile measurement has valid samples and PSD data
- **THEN** the analyzer records PSD method, PSD parameters, frequency band, integrated vibration energy, and sample-rate estimate for that measurement

#### Scenario: CoreXY angular projection is computed
- **WHEN** both required measured directions have valid energy data for a speed
- **THEN** the analyzer projects vibration energy over 0-360 degrees using CoreXY motor-speed decomposition and records projected energy by angle for that speed

#### Scenario: Projection is unavailable for incomplete data
- **WHEN** required direction data is missing or invalid for a speed
- **THEN** projected angle data for that speed is marked unavailable with diagnostics

#### Scenario: Avoid bands are detected
- **WHEN** vibration-energy peaks exceed configured thresholds
- **THEN** the analyzer records avoid bands with speed range, peak speed, energy value, and margin

#### Scenario: Preferred ranges are detected
- **WHEN** low-energy valleys satisfy configured width and energy thresholds
- **THEN** the analyzer records preferred speed ranges with speed bounds and supporting energy metrics

#### Scenario: Angle summaries are computed
- **WHEN** projected speed-profile data is available
- **THEN** the analyzer records per-speed minimum, maximum, variance, combined vibration metric, angle-energy summaries, and low-vibration angle ranges

#### Scenario: Z-labeled speed-profile measurements are ignored
- **WHEN** a capture includes Z-labeled measurements
- **THEN** the analyzer ignores them and records that Max 4 speed-profile analysis supports CoreXY X/Y directions only

#### Scenario: Speed-profile outputs are written by speed-limits analysis
- **WHEN** speed-limit analysis completes with valid or diagnostic speed-profile output
- **THEN** `analysis-speed-limits.json` includes speed-profile validation diagnostics, measurement energy, projection data, avoid bands, preferred ranges, angle summaries, warnings, and graph paths when graph generation succeeds

### Requirement: Observed Tested Ceilings
The analyzer SHALL report observed tested ceilings from the coupled candidate evidence without presenting untested values as proven safe.

#### Scenario: Passing candidates exist
- **WHEN** the candidate evidence contains one or more passing candidates and no invalidating diagnostics for those candidates
- **THEN** the analysis reports the highest passing tested velocity, highest passing tested acceleration, passing candidate envelope, and first failing or stopped candidates when present

#### Scenario: Sparse grid limits confidence
- **WHEN** the tested candidate grid is too sparse to identify a reliable boundary
- **THEN** the analysis reports the observed passing candidates and adds an insufficient-grid diagnostic to the recommendation evidence

#### Scenario: No passing candidates exist
- **WHEN** no candidate has enough evidence to be classified as passing
- **THEN** the analysis withholds observed max-limit conclusions and reports the blocking diagnostics

### Requirement: Recommended Motion Limits
The analyzer SHALL report conservative recommended limits separately from observed tested ceilings.

#### Scenario: Recommendations are evidence-backed
- **WHEN** motion-limit evidence, endstop-drift evidence, planner metadata, shaper evidence, and speed-profile evidence are sufficient
- **THEN** the analyzer reports recommended `max_velocity`, recommended `max_accel`, and recommended slicer motion speed guidance with evidence references and derating rationale

#### Scenario: Recommendations stay inside tested envelope
- **WHEN** the analyzer computes recommended limits
- **THEN** recommended values do not exceed the passing coupled candidate envelope, configured command maxima, or highest passing tested values

#### Scenario: Vibration evidence constrains slicer speed guidance
- **WHEN** speed-profile analysis finds vibration avoid bands or preferred speed ranges
- **THEN** recommended slicer motion speed guidance accounts for those ranges and records the vibration evidence used

#### Scenario: Insufficient evidence withholds recommendation
- **WHEN** required evidence for a recommended limit is missing, invalid, or contradicted by safety diagnostics
- **THEN** the analyzer withholds that recommended value and reports the exact missing or invalid evidence

### Requirement: Slicer Speed Guidance Scope
The analyzer SHALL label slicer speed output as motion-quality guidance, not material-flow capability.

#### Scenario: Slicer speed recommendation is emitted
- **WHEN** the analyzer emits slicer motion speed guidance
- **THEN** the summary and JSON state that the value excludes filament, nozzle, cooling, pressure-advance, extrusion-flow, and material-specific limits

#### Scenario: Proposed snippets are explicit
- **WHEN** the analyzer writes proposed config or slicer snippets
- **THEN** snippets are marked as operator-applied recommendations and are never applied automatically
