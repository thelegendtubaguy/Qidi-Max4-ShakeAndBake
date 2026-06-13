## 1. CLI Entry Point

- [x] 1.1 Add `shakeandbake analyze shaper <capture-file> --output-dir <dir>` command wiring.
- [x] 1.2 Parse command options for output directory, max smoothing, residual-vibration threshold, graph enablement, and JSON-only mode if supported by the project CLI conventions.
- [x] 1.3 Ensure the command does not import or initialize Klipper modules.

## 2. Validation Gate

- [x] 2.1 Load the capture artifact through the capture library.
- [x] 2.2 Stop analysis when capture validation returns unsupported schema, missing metadata, invalid sample shape, insufficient samples, nonmonotonic time, nonfinite samples, or constant signal.
- [x] 2.3 Select X and Y measurement blocks only and ignore Z-labeled measurements with a diagnostic.
- [x] 2.4 Write validation diagnostics to `analysis-shaper.json` when recommendations are blocked.

## 3. PSD Pipeline

- [x] 3.1 Derive sample rate from measurement timestamps and record sample-rate estimate plus frequency resolution.
- [x] 3.2 Remove per-axis median/DC offsets before frequency-domain processing.
- [x] 3.3 Implement Welch PSD with explicit window, segment length, overlap, and frequency range.
- [x] 3.4 Validate PSD arrays for nonempty, nonconstant, nonzero, and finite values.
- [x] 3.5 Detect resonance peaks with relative and absolute thresholds and record peak frequency, energy, and prominence.

## 4. Shaper Evaluation

- [x] 4.1 Implement candidate definitions for `zv`, `mzv`, `ei`, `2hump_ei`, and `3hump_ei` using independently written analyzer code.
- [x] 4.2 Calculate residual vibration, smoothing, and acceleration guidance for each candidate.
- [x] 4.3 Select a low-vibration candidate and a performance-oriented candidate when finite metrics satisfy configured constraints.
- [x] 4.4 Withhold recommendations and record diagnostics when candidate metrics are invalid or constraints cannot be satisfied.

## 5. Damping and LIS2DW Warnings

- [x] 5.1 Estimate damping ratio from dominant PSD peak half-power crossings using `peak / 2`.
- [x] 5.2 Record damping unavailable diagnostics when half-power crossings are missing or invalid.
- [x] 5.3 Add LIS2DW sample-rate, aliasing-risk, excessive-noise, and insufficient-signal warnings when metrics indicate those conditions.

## 6. Outputs

- [x] 6.1 Write `analysis-shaper.json` with source capture fingerprint, validation results, PSD metadata, peaks, candidates, selected recommendations, warnings, and diagnostics.
- [x] 6.2 Write a human-readable summary with one section per analyzed axis.
- [x] 6.3 Write `input-shaper.proposed.cfg` only when at least one axis has a valid recommendation.
- [x] 6.4 Write graph image files for valid X/Y PSD data and candidate summary when graph generation is enabled.
- [x] 6.5 Keep all derived files outside the raw capture artifact.

## 7. Tests and Fixtures

- [x] 7.1 Add fixtures for valid X-only, valid Y-only, and valid X/Y captures.
- [x] 7.2 Add invalid capture tests for empty data, one-sample data, nonmonotonic time, non-finite samples, constant signal, missing axis blocks, and Z-only captures.
- [x] 7.3 Add synthetic resonance fixtures with known peak frequencies and expected recommendation behavior.
- [x] 7.4 Add tests for damping estimation using PSD half-power `peak / 2` crossings.
- [x] 7.5 Add tests proving analyzer output does not modify raw capture files or printer configuration.
