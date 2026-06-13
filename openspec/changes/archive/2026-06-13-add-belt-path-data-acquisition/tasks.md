## 1. Command Registration

- [x] 1.1 Register `SHAKEANDBAKE_CAPTURE_BELTS` in the Shake&Bake Klipper extra.
- [x] 1.2 Add command help text and parameter parsing for supported belt-capture parameters.
- [x] 1.3 Reject unsupported kinematics and any Z-axis belt semantics.

## 2. Direction and Motion Planning

- [x] 2.1 Define CoreXY A direction `(1, -1, 0)` and B direction `(1, 1, 0)` constants.
- [x] 2.2 Build planned X/Y envelopes for both directions before motion.
- [x] 2.3 Run Max 4 preflight with the combined planned envelope.
- [x] 2.4 Stop before motion when preflight returns blocking findings.

## 3. Acquisition Lifecycle

- [x] 3.1 Snapshot input-shaper and velocity-limit state before temporary changes.
- [x] 3.2 Disable input shaper during A and B sampling.
- [x] 3.3 Acquire raw LIS2DW samples for A and B paths using matched sweep parameters.
- [x] 3.4 Restore input-shaper and velocity-limit state through cleanup paths.

## 4. Artifact Writing

- [x] 4.1 Write one capture artifact with A and B measurement blocks.
- [x] 4.2 Include path labels, direction vectors, sweep parameters, state snapshots, axes map, probe point, accelerometer identity, and preflight warnings.
- [x] 4.3 Report the capture path and measurement names in gcode output.
- [x] 4.4 Ensure command output contains no analysis results.

## 5. Tests

- [x] 5.1 Test command registration and parameter parsing.
- [x] 5.2 Test A/B direction metadata and matched parameter recording.
- [x] 5.3 Test refusal for unsafe printer states and out-of-bounds diagonal envelopes.
- [x] 5.4 Test successful artifact creation with fake accelerometer samples.
- [x] 5.5 Test forced failures during A capture, B capture, and artifact writing to verify state restoration.
