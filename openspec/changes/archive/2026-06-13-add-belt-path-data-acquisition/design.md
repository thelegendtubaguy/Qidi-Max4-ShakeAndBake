## Context

Max 4 is a CoreXY printer. A belt-path acquisition command exercises the two diagonal toolhead directions associated with the CoreXY motor paths: A `(1, -1, 0)` and B `(1, 1, 0)`. The command captures raw LIS2DW accelerometer samples for each path with identical sweep parameters, then writes a single raw capture artifact.

The command runs inside Klipper and must remain data-acquisition only. External analysis computes PSD curves, peak pairing, similarity metrics, and mechanical-health summaries. The Max 4 Z axis is bed-driven and not part of belt-path acquisition.

## Goals / Non-Goals

**Goals:**

- Register `SHAKEANDBAKE_CAPTURE_BELTS`.
- Run preflight and reject unsafe states before movement.
- Capture A and B CoreXY belt-path measurements with matched parameters.
- Record direction vectors, sweep parameters, probe point, accelerometer metadata, and preflight warnings in the capture artifact.
- Restore input-shaper and velocity-limit state through cleanup paths.

**Non-Goals:**

- No PSD comparison, peak pairing, graph generation, or health labels in Klipper.
- No Z-axis belt acquisition.
- No automatic config writes.
- No support for non-CoreXY kinematics.

## Decisions

### Direction mapping

Use explicit CoreXY direction vectors: A `(1, -1, 0)` and B `(1, 1, 0)`. Store both the logical path label and the vector in measurement metadata.

Alternative considered: infer belt path directions from kinematics at runtime. Explicit Max 4 mapping is simpler and easier to validate.

### Artifact shape

Write one capture artifact per command invocation with two measurement blocks named for A and B. Both blocks use the same sweep parameters unless the command fails before the second measurement, in which case no successful artifact is reported.

Alternative considered: write one file per belt path. A single artifact keeps paired captures and shared state together.

### Parameter surface

Support `FREQ_START`, `FREQ_END`, `HZ_PER_SEC`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, and `OUTPUT_DIR`. Use active `[resonance_tester]` defaults when command parameters are omitted.

Alternative considered: expose broad motion tuning parameters. A small surface reduces unsafe combinations.

### Analysis boundary

Command output reports readiness, warnings, capture path, and measurement names only. No similarity percentage, peak summary, or health indicator is emitted by the Klipper command.

Alternative considered: compute simple metrics in Klipper. Even simple metrics create dependency and timing pressure inside the printer process.

## Risks / Trade-offs

- [Risk] The second path can fail after the first path succeeds → Mitigation: restore state in cleanup paths and report failure without presenting a paired capture as complete.
- [Risk] Diagonal motion envelope can exceed safe X/Y bounds → Mitigation: preflight validates the complete planned envelope with margin.
- [Risk] Host load can affect long captures → Mitigation: preflight reports resource warnings and acquisition performs no analysis or plotting.
