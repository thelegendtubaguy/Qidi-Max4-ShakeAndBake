## 1. Speed-Limit Data Model and Fixtures

- [ ] 1.1 Define speed-limit evidence metadata structures for phases, candidate records, trigger observations, trigger drift, closed-loop observations, safety stops, and recommendation inputs.
- [ ] 1.2 Add capture fixture builders for valid speed-limit evidence artifacts with baseline scans, candidate records, shaper measurements, and speed-profile measurements.
- [ ] 1.3 Add invalid fixture builders for missing baseline, malformed candidate records, unavailable trigger observations, closed-loop fault records, and incomplete vibration phases.
- [ ] 1.4 Extend capture validation or speed-limit analyzer validation to require speed-limit-specific metadata only for `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` artifacts.

## 2. Command Registration and Parameter Parsing

- [ ] 2.1 Register `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` in the Klipper extra command surface.
- [ ] 2.2 Add typed parsing for `MAX_SPEED`, `SPEED_INCREMENT`, `ACCEL_MIN`, `ACCEL_MAX`, `ACCEL_INCREMENT`, speed-profile acceleration/travel/segment parameters, `MARGIN`, `ENDSTOP_SAMPLES`, `MAX_DRIFT`, `MAX_CANDIDATES`, `ACCEL_CHIP`, and `OUTPUT_DIR`.
- [ ] 2.3 Reject Z-axis, non-CoreXY, nonpositive range, excessive candidate count, and out-of-config-limit parameters before motion.
- [ ] 2.4 Ensure command import tests prove no numerical, plotting, or analyzer modules are imported by the Klipper plugin.

## 3. Phase Planning and Preflight

- [ ] 3.1 Implement the default phase plan for baseline scans, coupled stress candidates, X/Y shaper sweeps, and 45/135 degree speed-profile measurements.
- [ ] 3.2 Implement bounded coupled velocity/acceleration candidate grid generation with stable candidate identifiers.
- [ ] 3.3 Compute the complete planned X/Y motion envelope across all enabled phases.
- [ ] 3.4 Run Max 4 preflight against the complete planned envelope and block before motion on blocking findings.
- [ ] 3.5 Report planned phase names, candidate count, speed range, acceleration range, and safety thresholds before acquisition motion starts.

## 4. Endstop Trigger Evidence

- [ ] 4.1 Add adapter methods for low-speed X and Y endstop-trigger scans that return commanded trigger coordinate, side, speed, timestamp, and availability.
- [ ] 4.2 Implement baseline trigger scans with configurable sample count for X and Y.
- [ ] 4.3 Compute and record baseline trigger spread and the configured drift safety threshold.
- [ ] 4.4 Block stress candidates when baseline trigger observations are missing or unavailable.
- [ ] 4.5 Implement post-candidate X/Y trigger scans and drift recording against baseline.
- [ ] 4.6 Stop candidate escalation, rehome X/Y when possible, and record safety-stop metadata when trigger drift exceeds threshold or scan collection fails.

## 5. QIDI Closed-Loop Observations

- [ ] 5.1 Add adapter methods to snapshot available `[closed_loop x]`, `[closed_loop y]`, and `cl_interface` status without requiring standard X/Y TMC sections.
- [ ] 5.2 Record raw closed-loop field names, values, axis or motor labels, observation time, and associated phase or candidate id.
- [ ] 5.3 Detect explicit closed-loop fault, alarm, motor-position-error, and no-response states when exposed by runtime status.
- [ ] 5.4 Stop candidate escalation, rehome X/Y when possible, and record safety-stop metadata on explicit closed-loop unsafe states.
- [ ] 5.5 Record nonblocking diagnostics when closed-loop status is unavailable but endstop-trigger evidence is usable.

## 6. Motion Candidate Execution

- [ ] 6.1 Implement stress-motion execution for Cartesian X candidates within the planned envelope.
- [ ] 6.2 Implement stress-motion execution for Cartesian Y candidates within the planned envelope.
- [ ] 6.3 Implement CoreXY diagonal or motor-path stress candidates that exercise both X/Y motors.
- [ ] 6.4 Record candidate id, velocity, acceleration, directions, repetitions, segment length, planner settings, and planned envelope before each candidate.
- [ ] 6.5 Restore or reset to a known homed X/Y state between candidate regions and after unsafe candidates.
- [ ] 6.6 Add forced-motion-error tests proving cleanup and metadata preservation for interrupted candidate execution.

## 7. Vibration Evidence Phases

- [ ] 7.1 Reuse or factor X/Y shaper acquisition so the speed-limit command can include shaper measurement blocks in the same artifact.
- [ ] 7.2 Generate and validate the speed-profile grid from `MAX_SPEED` and `SPEED_INCREMENT` with positive speeds, configured-limit checks, and measurement-count bounds.
- [ ] 7.3 Define Max 4 CoreXY 45 degree and 135 degree speed-profile direction metadata with direction angle and direction vector values.
- [ ] 7.4 Build the speed-profile measurement list and planned envelope from the speed grid, direction metadata, profile acceleration, travel speed, and segment-size parameters.
- [ ] 7.5 Capture raw LIS2DW samples for each speed-profile speed/direction measurement in the same artifact as the motion-limit evidence.
- [ ] 7.6 Record speed grid, direction vectors, direction angles, segment planning metadata, probe point, axes map, accelerometer identity, preflight warnings, and state snapshots for speed-profile measurements.
- [ ] 7.7 Record failed shaper or speed-profile phases explicitly while preserving already-collected motion-limit evidence when artifact writing remains possible.
- [ ] 7.8 Ensure vibration evidence phases disable input shaper only while required and restore state through shared cleanup paths.

## 8. Artifact Writing and Command Output

- [ ] 8.1 Write one raw `.sbcapture.json` artifact for the full speed-limit evidence run.
- [ ] 8.2 Include command parameters, phase plan, planned motion envelope, probe point, axes map, accelerometer identity, input-shaper pre-state, velocity-limit pre-state, square-corner velocity, fan/heater/chamber snapshot, host-resource warnings, and restoration status.
- [ ] 8.3 Include candidate records, trigger observations, drift values, safety thresholds, closed-loop observations, planner settings, and safety-stop reasons.
- [ ] 8.4 Ensure command output reports capture status and artifact path without final limits, graphs, or proposed config snippets.
- [ ] 8.5 Add write-failure and validation-failure tests proving temporary state restoration and clear diagnostics.

## 9. External Analyzer CLI and Validation

- [ ] 9.1 Add `shakeandbake analyze speed-limits <capture> --output-dir <dir>` CLI wiring.
- [ ] 9.2 Parse analyzer options for frequency band, angular resolution, avoid-band thresholds, preferred-range thresholds, graph enablement, and summary-only behavior.
- [ ] 9.3 Validate speed-limit artifacts for required metadata, candidate records, trigger observations, closed-loop records, and enabled vibration measurements.
- [ ] 9.4 Validate embedded speed-profile completeness for expected speeds and required 45 degree and 135 degree directions.
- [ ] 9.5 Reject unsupported schema, wrong command type, missing baseline evidence, malformed candidate records, invalid trigger observations, missing speed-profile directions, missing speeds, invalid required measurement samples, and invalid sample rates with explicit diagnostics.
- [ ] 9.6 Ignore Z-labeled speed-profile measurements with diagnostics.
- [ ] 9.7 Keep derived JSON, summaries, graphs, reports, and proposed snippets separate from the raw capture artifact.

## 10. Motion-Limit Classification

- [ ] 10.1 Classify candidate evidence using trigger drift, baseline spread, safety thresholds, scan availability, and explicit closed-loop unsafe states.
- [ ] 10.2 Build a coupled passing/failing velocity/acceleration envelope from classified candidates.
- [ ] 10.3 Identify highest passing tested velocity, highest passing tested acceleration, passing envelope, first failing candidates, and stopped candidate regions.
- [ ] 10.4 Emit insufficient-grid diagnostics when candidate spacing or coverage cannot support a reliable boundary.
- [ ] 10.5 Withhold observed max-limit conclusions when no candidates have enough evidence to be classified as passing.

## 11. Speed-Profile Analysis and Recommendation Outputs

- [ ] 11.1 Compute PSD for each valid embedded speed-profile speed/direction measurement.
- [ ] 11.2 Integrate vibration energy over the configured frequency band and record PSD method, PSD parameters, frequency band, sample-rate estimate, and energy value per measurement.
- [ ] 11.3 Project valid 45 degree and 135 degree speed-profile measurements over 0-360 degrees using CoreXY motor-speed decomposition.
- [ ] 11.4 Compute per-speed minimum, maximum, variance, combined vibration metric, angle-energy summaries, and low-vibration angle ranges.
- [ ] 11.5 Detect avoid bands around vibration-energy peaks with configurable margins.
- [ ] 11.6 Detect preferred speed ranges from low-energy valleys with minimum-width filtering.
- [ ] 11.7 Combine motion-limit classification with shaper analysis evidence and speed-profile vibration evidence.
- [ ] 11.8 Compute recommended `max_velocity`, recommended `max_accel`, and recommended slicer motion speed guidance inside the passing candidate envelope.
- [ ] 11.9 Apply conservative derating and clamp recommendations by vibration avoid bands, preferred speed ranges, shaper residual/smoothing evidence, configured command maxima, and evidence-quality diagnostics.
- [ ] 11.10 Withhold individual recommendations when required evidence is missing, invalid, or contradicted by safety diagnostics.
- [ ] 11.11 Write `analysis-speed-limits.json` with observed ceilings, recommendations, speed-profile validation diagnostics, measurement energy, projection data, avoid bands, preferred ranges, angle summaries, warnings, evidence references, derating rationale, diagnostics, graph paths, and source capture reference.
- [ ] 11.12 Write graph files for speed-vs-angle heatmap, per-speed energy, avoid bands, and preferred ranges when graph generation succeeds.
- [ ] 11.13 Write a human-readable summary and proposed operator-applied config/slicer snippets that are never applied automatically.
- [ ] 11.14 Label slicer speed guidance as motion-quality guidance excluding filament, nozzle, cooling, pressure-advance, extrusion-flow, and material-specific limits.

## 12. Tests and Integration Coverage

- [ ] 12.1 Add command registration and parameter-validation tests for valid defaults and rejected unsafe inputs.
- [ ] 12.2 Add phase-planning tests for candidate count, envelope bounds, X/Y/CoreXY direction coverage, and stable candidate ids.
- [ ] 12.3 Add preflight refusal tests for printing, paused, virtual-SD active, homing, not ready, missing accelerometer, and out-of-bounds envelope states.
- [ ] 12.4 Add state-restoration tests for success, command error, motion error, sampling error, endstop-scan error, closed-loop error, and artifact-write error.
- [ ] 12.5 Add analyzer tests for valid artifacts, invalid artifacts, sparse grids, first failures, closed-loop faults, missing vibration phases, speed-profile missing direction, missing speed, invalid sample, degenerate PSD, known avoid peaks, known preferred valleys, projection output shape, graph failure handling, and recommendation withholding.
- [ ] 12.6 Run the focused unit test suite for capture validation, Max 4 preflight, speed-limit acquisition, and speed-limit analyzer behavior.
