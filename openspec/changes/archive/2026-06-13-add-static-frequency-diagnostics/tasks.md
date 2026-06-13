## 1. Printer Command

- [x] 1.1 Register `SHAKEANDBAKE_EXCITE` in the Shake&Bake Klipper extra.
- [x] 1.2 Parse `AXIS`, `FREQUENCY`, `DURATION`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, `RECORD`, and `OUTPUT_DIR` parameters.
- [x] 1.3 Validate frequency, duration, axis, and bounds before motion.
- [x] 1.4 Reject `AXIS=Z` and unsupported axis values before preflight motion checks.

## 2. Excitation Lifecycle

- [x] 2.1 Map X, Y, A, and B to direction vectors.
- [x] 2.2 Build and validate the fixed-frequency motion envelope.
- [x] 2.3 Run Max 4 preflight and stop before motion on blocking findings.
- [x] 2.4 Snapshot input-shaper and velocity-limit state before temporary changes.
- [x] 2.5 Disable input shaper during excitation.
- [x] 2.6 Execute fixed-frequency pulses for the validated duration.
- [x] 2.7 Restore input-shaper and velocity-limit state through cleanup paths.

## 3. Optional Recording

- [x] 3.1 Capture raw LIS2DW samples when `RECORD=1`.
- [x] 3.2 Write a versioned static-frequency capture artifact with axis, direction vector, frequency, duration, samples, state snapshots, and warnings.
- [x] 3.3 Report capture path when recording succeeds.
- [x] 3.4 Report excitation completion without artifact path when `RECORD=0`.

## 4. External Analysis

- [x] 4.1 Add `shakeandbake analyze static-frequency <capture-file> --output-dir <dir>` command wiring.
- [x] 4.2 Validate capture metadata, axis label, timestamps, samples, and sample-rate estimate.
- [x] 4.3 Compute spectrogram and cumulative energy over time for valid captures.
- [x] 4.4 Write `analysis-static-frequency.json`, a human-readable summary, and graph files when graph generation succeeds.

## 5. Tests

- [x] 5.1 Test command registration and parameter validation.
- [x] 5.2 Test X, Y, A, and B direction mapping.
- [x] 5.3 Test Z-axis and unsupported-axis rejection.
- [x] 5.4 Test unsafe-state refusal before motion.
- [x] 5.5 Test successful excitation with and without recording.
- [x] 5.6 Test forced failures during motion, sampling, and writing to verify state restoration.
- [x] 5.7 Test static-frequency analyzer diagnostics and output files.
