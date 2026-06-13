## 1. CLI Entry Point

- [ ] 1.1 Add `shakeandbake analyze speed-profile <capture-file> --output-dir <dir>` command wiring.
- [ ] 1.2 Parse options for output directory, frequency band, angular resolution, avoid-band thresholds, preferred-range thresholds, and graph enablement.
- [ ] 1.3 Ensure the speed-profile analyzer does not import or initialize Klipper modules.

## 2. Capture Validation

- [ ] 2.1 Load capture artifacts through the capture library.
- [ ] 2.2 Select 45 degree and 135 degree CoreXY measurement blocks by metadata.
- [ ] 2.3 Validate expected speed grid completeness.
- [ ] 2.4 Validate monotonic time, finite samples, sample count, nonconstant signal, and usable sample rate per measurement.
- [ ] 2.5 Ignore Z-labeled measurements with diagnostics.

## 3. PSD Energy Pipeline

- [ ] 3.1 Compute PSD for every valid speed/direction measurement.
- [ ] 3.2 Integrate vibration energy over the configured frequency band.
- [ ] 3.3 Record PSD method, frequency band, sample-rate estimate, and energy value per measurement.
- [ ] 3.4 Emit diagnostics for invalid PSD arrays and insufficient signal.

## 4. CoreXY Projection and Range Detection

- [ ] 4.1 Implement CoreXY motor-speed decomposition for angular projection.
- [ ] 4.2 Project valid measured energy data over configured 0-360 degree angular resolution.
- [ ] 4.3 Compute per-speed minimum, maximum, variance, and combined vibration metric.
- [ ] 4.4 Detect avoid bands around energy peaks with configurable margins.
- [ ] 4.5 Detect preferred speed ranges from low-energy valleys with minimum-width filtering.
- [ ] 4.6 Compute angle-energy summaries and low-vibration angle ranges.

## 5. Outputs

- [ ] 5.1 Write `analysis-speed-profile.json` with source capture fingerprint, validation diagnostics, measurement energy, projection data, avoid bands, preferred ranges, angle summaries, and warnings.
- [ ] 5.2 Write a human-readable speed-profile summary.
- [ ] 5.3 Write graph files for speed-vs-angle heatmap, per-speed energy, avoid bands, and preferred ranges when graph generation succeeds.
- [ ] 5.4 Keep all derived outputs separate from the raw capture artifact.

## 6. Tests

- [ ] 6.1 Add valid speed-profile fixture tests with 45 degree and 135 degree directions.
- [ ] 6.2 Add tests for missing direction, missing speed, invalid sample, degenerate PSD, and Z-labeled measurement handling.
- [ ] 6.3 Add synthetic energy fixtures with known avoid peaks and preferred valleys.
- [ ] 6.4 Test CoreXY projection output shape and angle resolution.
- [ ] 6.5 Test graph failure handling without losing JSON output.
