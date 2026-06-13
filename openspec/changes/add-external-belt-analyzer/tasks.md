## 1. CLI Entry Point

- [ ] 1.1 Add `shakeandbake analyze belts <capture-file> --output-dir <dir>` command wiring.
- [ ] 1.2 Parse output, graph, threshold, and JSON options following project CLI conventions.
- [ ] 1.3 Ensure the belt analyzer does not import or initialize Klipper modules.

## 2. Capture and PSD Validation

- [ ] 2.1 Load capture artifacts through the capture library.
- [ ] 2.2 Select A and B path measurement blocks by metadata path label.
- [ ] 2.3 Return `missing_path` diagnostics when either path is absent.
- [ ] 2.4 Validate monotonic time, finite samples, sample count, nonconstant signal, and usable sample rate.
- [ ] 2.5 Compute and validate PSD arrays for finite, nonempty, nonzero, and nonconstant values.

## 3. Peak Detection and Pairing

- [ ] 3.1 Interpolate A and B PSDs onto a common frequency grid.
- [ ] 3.2 Detect peaks using relative and absolute thresholds.
- [ ] 3.3 Pair peaks by bounded frequency proximity.
- [ ] 3.4 Record paired peaks, unpaired A peaks, unpaired B peaks, frequency deltas, and amplitude ratios.

## 4. Comparison Metrics

- [ ] 4.1 Compute normalized area difference between A and B PSD curves.
- [ ] 4.2 Compute correlation only when both PSD arrays are valid for correlation.
- [ ] 4.3 Record correlation unavailable diagnostics instead of `NaN`.
- [ ] 4.4 Generate warnings for excessive peak counts, unpaired peaks, insufficient signal, and aliasing risk.

## 5. Outputs

- [ ] 5.1 Write `analysis-belts.json` with source capture fingerprint, validation diagnostics, PSD metadata, peaks, pairs, metrics, warnings, and motor metadata.
- [ ] 5.2 Write a human-readable belt comparison summary.
- [ ] 5.3 Write graph files for A/B PSD overlay and peak-pairing visualization when graph generation succeeds.
- [ ] 5.4 Keep derived outputs separate from the raw capture artifact.

## 6. Tests

- [ ] 6.1 Add valid paired A/B fixture tests.
- [ ] 6.2 Add missing A, missing B, invalid sample, constant signal, non-finite sample, and degenerate PSD tests.
- [ ] 6.3 Add paired and unpaired peak fixture tests.
- [ ] 6.4 Test correlation unavailable behavior for constant PSD arrays.
- [ ] 6.5 Test QIDI closed-loop motor metadata reporting.
