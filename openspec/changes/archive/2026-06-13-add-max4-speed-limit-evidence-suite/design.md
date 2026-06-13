## Context

Shake&Bake already separates Max 4 acquisition from external analysis. The speed-limit workflow keeps that boundary: the printer runs one bounded evidence capture and writes one raw artifact, then `shakeandbake analyze speed-limits <capture>` computes limits, recommendations, summaries, and graphs on another host.

The command targets QIDI Max 4 CoreXY X/Y motion only. The stock Max 4 exposes X/Y closed-loop metadata and status through QIDI-specific objects, but Klipper still needs independent position-loss evidence because the closed-loop system does not provide cartesian position recovery semantics to Shake&Bake.

## Goals / Non-Goals

**Goals:**

- Register `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` as the one printer-side command for speed-limit evidence capture.
- Capture enough evidence to analyze observed tested ceilings for `max_velocity`, `max_accel`, and slicer motion speed guidance.
- Measure X/Y missed-step evidence through repeatable endstop-trigger scans before and after stress-motion candidates.
- Test velocity and acceleration as coupled candidate pairs instead of independent one-dimensional maxima.
- Include X/Y shaper sweeps and speed/direction vibration measurements in the same artifact when requested by the command defaults.
- Analyze embedded speed-profile measurements with PSD energy, CoreXY angular projection, avoid bands, preferred ranges, and angle summaries in the external speed-limits analyzer.
- Record available QIDI X/Y closed-loop status and coder observations as supplemental evidence.
- Keep final classification, graphs, proposed config snippets, and recommendations outside Klipper.

**Non-Goals:**

- No automatic edits to `printer.cfg`, slicer profiles, or saved variables.
- No filament, nozzle, cooling, pressure-advance, flow-rate, or extrusion-quality calibration.
- No Z-axis speed profiling, Z resonance calibration, or Z missed-step detection.
- No claim that an untested value beyond the highest passing candidate is safe.
- No dependency on standard X/Y TMC driver sections.

## Decisions

### Single orchestration command

`SHAKEANDBAKE_CAPTURE_SPEED_LIMITS` runs the complete printer-side capture sequence and writes one `.sbcapture.json` artifact. The command accepts bounded override parameters such as `MAX_SPEED`, `SPEED_INCREMENT`, `ACCEL_MIN`, `ACCEL_MAX`, `ACCEL_INCREMENT`, speed-profile acceleration and segment-size parameters, `MARGIN`, `ENDSTOP_SAMPLES`, `MAX_DRIFT`, `MAX_CANDIDATES`, `ACCEL_CHIP`, and `OUTPUT_DIR`.

Alternative considered: separate commands for endstop repeatability, motion limits, shaper captures, and speed profile. Separate commands make debugging easier, but they do not satisfy the single-command user workflow.

### Endstop trigger scans as the primary position-loss evidence

The acquisition sequence records low-speed X and Y endstop-trigger observations before stress motion, repeats trigger observations after each candidate, and restores the machine to a known homed state before continuing. A candidate is considered unsafe for continued escalation when observed trigger drift exceeds the command safety threshold or when a required trigger observation cannot be collected.

Alternative considered: rely only on QIDI closed-loop coder values. The closed-loop values are useful evidence, but their exact scaling and cartesian interpretation are not stable enough to be the sole missed-step signal.

### Coupled velocity/acceleration candidate grid

The planner tests candidate pairs such as `(velocity, accel)` and records the full pass/fail envelope. The analyzer derives scalar `max_velocity` and `max_accel` recommendations from the passing envelope rather than treating velocity and acceleration as independent limits.

Alternative considered: binary-search velocity and acceleration independently. Independent searches can recommend an impossible pair such as a high velocity that only passed at low acceleration and a high acceleration that only passed at low velocity.

### Supplemental QIDI closed-loop observations

The command snapshots available `[closed_loop x]`, `[closed_loop y]`, and `cl_interface` status before and after baseline scans and candidate motion. Explicit fault, alarm, position-error, no-response, or shutdown-adjacent states stop escalation and are recorded in the raw artifact. Numeric coder fields are recorded with raw names, signs, and values, and the analyzer treats them as supporting evidence unless fixtures establish reliable scaling.

Alternative considered: hide closed-loop fields until fully decoded. Recording raw status fields preserves evidence for Max 4 analysis without making unverified semantics normative.

### Combined motion and vibration evidence artifact

The raw artifact contains non-analysis evidence blocks for baseline trigger scans, candidate stress results, closed-loop observations, planner settings, and safety stops. It also contains accelerometer measurement blocks for X/Y shaper sweeps and speed/direction vibration measurements when those phases are enabled. Speed-profile measurements use the Max 4 CoreXY 45 degree and 135 degree directions, record speed-grid metadata, store direction angles and vectors, and preserve segment planning metadata so external analysis can reproduce duration and movement context. The artifact uses the existing capture schema root and stores speed-limit-specific records in typed metadata sections.

Alternative considered: write multiple artifacts from one command. One artifact is easier for users to move to another host and prevents mismatched analysis inputs.

### External recommendation engine

`shakeandbake analyze speed-limits <capture> --output-dir <dir>` validates the artifact, computes the tested passing envelope, identifies first failing candidates, evaluates shaper evidence, computes speed-profile PSD energy, projects 45/135 degree measurements over 0-360 degrees with CoreXY motor-speed decomposition, detects avoid bands and preferred ranges, and writes derived JSON, summary, graphs, and proposed config snippets. JSON is authoritative; graph failures do not invalidate analysis JSON.

Alternative considered: emit recommendations from the printer command. The Max 4 host is constrained, and recommendation logic needs numerical processing, graphing, and fixture-driven tuning outside Klipper.

### Conservative recommendation semantics

The analyzer reports observed tested ceilings separately from recommended limits. Observed ceilings are the highest passing values in the tested grid. Recommended limits are derated inside the passing envelope and clamped by vibration avoid bands, shaper residual/smoothing evidence, planner settings, and missing-evidence diagnostics.

Alternative considered: report one best value. A single value hides the boundary conditions, first failures, and evidence quality that make the recommendation trustworthy.

## Risks / Trade-offs

- [Risk] Endstop trigger scans can add time and mechanical wear → Mitigation: use low-speed scans, configurable sample counts, bounded candidate count, and stop escalation after the first unsafe result in a candidate region.
- [Risk] A single full capture can take a long time → Mitigation: report planned phase count and estimated duration before motion, enforce `MAX_CANDIDATES`, and allow explicit phase disabling while keeping the default one-command path complete.
- [Risk] Baseline endstop noise can look like missed steps → Mitigation: establish a baseline distribution before stress testing and require drift beyond baseline plus margin before unsafe escalation.
- [Risk] Closed-loop coder values can be misinterpreted on CoreXY → Mitigation: store raw motor-level fields, record the CoreXY candidate direction, and use endstop drift as the primary cartesian position-loss signal.
- [Risk] Recommended slicer speed can be mistaken for filament flow capacity → Mitigation: label it as slicer motion speed guidance and exclude extrusion/material capability from the analyzer contract.
- [Risk] Motion-limit recommendations can be overconfident near sparse grid edges → Mitigation: report grid spacing, first failing candidates, evidence quality, and withhold recommendations when the tested grid is insufficient.
