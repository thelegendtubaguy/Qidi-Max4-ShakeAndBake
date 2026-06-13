## 1. Command Registration

- [ ] 1.1 Register `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE` in the Shake&Bake Klipper extra.
- [ ] 1.2 Add parameter parsing for `MAX_SPEED`, `SPEED_INCREMENT`, `ACCEL`, `TRAVEL_SPEED`, `SIZE`, `ACCEL_CHIP`, and `OUTPUT_DIR`.
- [ ] 1.3 Reject unsupported axis or Z-axis profiling parameters.

## 2. Planning and Preflight

- [ ] 2.1 Generate the positive bounded speed grid from command parameters.
- [ ] 2.2 Define 45 degree and 135 degree CoreXY direction metadata.
- [ ] 2.3 Build the planned measurement list and motion envelope.
- [ ] 2.4 Validate measurement count, configured velocity limits, and X/Y bounds.
- [ ] 2.5 Run Max 4 preflight and stop before motion on blocking findings.

## 3. Acquisition Lifecycle

- [ ] 3.1 Snapshot input-shaper and velocity-limit state before temporary changes.
- [ ] 3.2 Disable input shaper during speed-profile sampling.
- [ ] 3.3 Capture raw LIS2DW samples for every planned speed/direction measurement.
- [ ] 3.4 Record segment planning metadata for low-speed and high-speed measurements.
- [ ] 3.5 Restore input-shaper and velocity-limit state through cleanup paths.

## 4. Artifact Writing

- [ ] 4.1 Write one capture artifact containing all speed/direction measurement blocks.
- [ ] 4.2 Include speed grid, direction vectors, segment metadata, state snapshots, axes map, probe point, accelerometer identity, and preflight warnings.
- [ ] 4.3 Report capture path and measurement count in gcode output.
- [ ] 4.4 Ensure command output contains no speed-profile analysis results.

## 5. Tests

- [ ] 5.1 Test command registration and parameter validation.
- [ ] 5.2 Test speed grid construction and excessive-measurement rejection.
- [ ] 5.3 Test direction metadata for 45 degree and 135 degree measurements.
- [ ] 5.4 Test unsafe-state and out-of-bounds refusal before motion.
- [ ] 5.5 Test successful capture artifact creation with fake accelerometer samples.
- [ ] 5.6 Test forced failures during sampling and writing to verify state restoration.
