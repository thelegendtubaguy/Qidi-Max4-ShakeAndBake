## 1. Printer Command

- [ ] 1.1 Register `SHAKEANDBAKE_EXCITE` in the Shake&Bake Klipper extra.
- [ ] 1.2 Parse `AXIS`, `FREQUENCY`, `DURATION`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, `RECORD`, and `OUTPUT_DIR` parameters.
- [ ] 1.3 Validate frequency, duration, axis, and bounds before motion.
- [ ] 1.4 Reject `AXIS=Z` and unsupported axis values before preflight motion checks.

## 2. Excitation Lifecycle

- [ ] 2.1 Map X, Y, A, and B to direction vectors.
- [ ] 2.2 Build and validate the fixed-frequency motion envelope.
- [ ] 2.3 Run Max 4 preflight and stop before motion on blocking findings.
- [ ] 2.4 Snapshot input-shaper and velocity-limit state before temporary changes.
- [ ] 2.5 Disable input shaper during excitation.
- [ ] 2.6 Execute fixed-frequency pulses for the validated duration.
- [ ] 2.7 Restore input-shaper and velocity-limit state through cleanup paths.

## 3. Optional Recording

- [ ] 3.1 Capture raw LIS2DW samples when `RECORD=1`.
- [ ] 3.2 Write a versioned static-frequency capture artifact with axis, direction vector, frequency, duration, samples, state snapshots, and warnings.
- [ ] 3.3 Report capture path when recording succeeds.
- [ ] 3.4 Report excitation completion without artifact path when `RECORD=0`.

## 4. External Analysis

- [ ] 4.1 Add `shakeandbake analyze static-frequency <capture-file> --output-dir <dir>` command wiring.
- [ ] 4.2 Validate capture metadata, axis label, timestamps, samples, and sample-rate estimate.
- [ ] 4.3 Compute spectrogram and cumulative energy over time for valid captures.
- [ ] 4.4 Write `analysis-static-frequency.json`, a human-readable summary, and graph files when graph generation succeeds.

## 5. Tests

- [ ] 5.1 Test command registration and parameter validation.
- [ ] 5.2 Test X, Y, A, and B direction mapping.
- [ ] 5.3 Test Z-axis and unsupported-axis rejection.
- [ ] 5.4 Test unsafe-state refusal before motion.
- [ ] 5.5 Test successful excitation with and without recording.
- [ ] 5.6 Test forced failures during motion, sampling, and writing to verify state restoration.
- [ ] 5.7 Test static-frequency analyzer diagnostics and output files.
