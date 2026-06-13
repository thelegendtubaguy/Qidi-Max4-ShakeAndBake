## 1. CLI Entry Point

- [ ] 1.1 Add `shakeandbake analyze shaper <capture-file> --output-dir <dir>` command wiring.
- [ ] 1.2 Parse command options for output directory, max smoothing, residual-vibration threshold, graph enablement, and JSON-only mode if supported by the project CLI conventions.
- [ ] 1.3 Ensure the command does not import or initialize Klipper modules.

## 2. Validation Gate

- [ ] 2.1 Load the capture artifact through the capture library.
- [ ] 2.2 Stop analysis when capture validation returns unsupported schema, missing metadata, invalid sample shape, insufficient samples, nonmonotonic time, nonfinite samples, or constant signal.
- [ ] 2.3 Select X and Y measurement blocks only and ignore Z-labeled measurements with a diagnostic.
- [ ] 2.4 Write validation diagnostics to `analysis-shaper.json` when recommendations are blocked.

## 3. PSD Pipeline

- [ ] 3.1 Derive sample rate from measurement timestamps and record sample-rate estimate plus frequency resolution.
- [ ] 3.2 Remove per-axis median/DC offsets before frequency-domain processing.
- [ ] 3.3 Implement Welch PSD with explicit window, segment length, overlap, and frequency range.
- [ ] 3.4 Validate PSD arrays for nonempty, nonconstant, nonzero, and finite values.
- [ ] 3.5 Detect resonance peaks with relative and absolute thresholds and record peak frequency, energy, and prominence.

## 4. Shaper Evaluation

- [ ] 4.1 Implement candidate definitions for `zv`, `mzv`, `ei`, `2hump_ei`, and `3hump_ei` using independently written analyzer code.
- [ ] 4.2 Calculate residual vibration, smoothing, and acceleration guidance for each candidate.
- [ ] 4.3 Select a low-vibration candidate and a performance-oriented candidate when finite metrics satisfy configured constraints.
- [ ] 4.4 Withhold recommendations and record diagnostics when candidate metrics are invalid or constraints cannot be satisfied.

## 5. Damping and LIS2DW Warnings

- [ ] 5.1 Estimate damping ratio from dominant PSD peak half-power crossings using `peak / 2`.
- [ ] 5.2 Record damping unavailable diagnostics when half-power crossings are missing or invalid.
- [ ] 5.3 Add LIS2DW sample-rate, aliasing-risk, excessive-noise, and insufficient-signal warnings when metrics indicate those conditions.

## 6. Outputs

- [ ] 6.1 Write `analysis-shaper.json` with source capture fingerprint, validation results, PSD metadata, peaks, candidates, selected recommendations, warnings, and diagnostics.
- [ ] 6.2 Write a human-readable summary with one section per analyzed axis.
- [ ] 6.3 Write `input-shaper.proposed.cfg` only when at least one axis has a valid recommendation.
- [ ] 6.4 Write graph image files for valid X/Y PSD data and candidate summary when graph generation is enabled.
- [ ] 6.5 Keep all derived files outside the raw capture artifact.

## 7. Tests and Fixtures

- [ ] 7.1 Add fixtures for valid X-only, valid Y-only, and valid X/Y captures.
- [ ] 7.2 Add invalid capture tests for empty data, one-sample data, nonmonotonic time, non-finite samples, constant signal, missing axis blocks, and Z-only captures.
- [ ] 7.3 Add synthetic resonance fixtures with known peak frequencies and expected recommendation behavior.
- [ ] 7.4 Add tests for damping estimation using PSD half-power `peak / 2` crossings.
- [ ] 7.5 Add tests proving analyzer output does not modify raw capture files or printer configuration.
