## Context

Shake&Bake analyzer commands run outside Klipper against raw capture artifacts produced by Max 4 data acquisition. The analyzer may use numerical and plotting dependencies in an isolated environment because it does not execute in Klipper's timing-sensitive process.

The analyzer consumes X/Y measurement blocks from a capture artifact, validates the data, estimates sample rate from monotonic timestamps, removes DC/gravity offsets, computes PSD summaries, detects resonance peaks, evaluates input-shaper candidates, and writes derived outputs. Derived outputs never overwrite raw captures.

The Max 4 uses a stock toolhead LIS2DW accelerometer with known aliasing/noise concerns. Analyzer output must include sample-rate estimates and signal-quality warnings. The Max 4 Z axis is bed-driven and not belt-driven; the analyzer must not process Z-axis movement as a shaper calibration input.

## Goals / Non-Goals

**Goals:**

- Provide an external CLI command for X/Y shaper analysis from Shake&Bake capture artifacts.
- Validate captures before numerical processing and return explicit diagnostics for invalid data.
- Compute PSD and resonance peak summaries for each valid X/Y measurement.
- Evaluate input-shaper candidates and emit a proposed `[input_shaper]` config snippet when signal quality supports recommendations.
- Write derived JSON, graph image, human-readable summary, and proposed config snippet files next to or under a chosen output directory.
- Report LIS2DW sample-rate, noise, aliasing, and repeatability warnings when detected by available data.

**Non-Goals:**

- No Klipper command registration or printer communication.
- No raw data acquisition.
- No writes to `printer.cfg`.
- No belt comparison, speed-profile analysis, static-frequency analysis, or Z-axis shaper analysis.
- No dependence on external GPL implementation code, strings, plotting layout, compressed schema, or helper implementations.

## Decisions

### CLI shape

Provide `shakeandbake analyze shaper <capture-file> --output-dir <dir>`. The command reads one capture artifact, selects X/Y measurement blocks, validates data, and writes derived outputs. Command exit status is nonzero when validation blocks analysis or output writing fails.

Alternative considered: a single generic `analyze` command with inferred behavior. Explicit subcommands make task-specific validation and output contracts easier to test.

### Validation before computation

Use the capture library validation result before running PSD or shaper calculations. Add analyzer-level checks for axis presence, minimum duration, usable sample rate, nonempty PSD, nonconstant PSD, and finite numeric arrays. Invalid data produces JSON diagnostics and no recommendation.

Alternative considered: let NumPy/SciPy exceptions surface. Raw exceptions produce unstable CLI behavior and make degenerate LIS2DW cases harder to understand.

### PSD computation

Use monotonic sample time to derive sample rate. Remove per-axis median/DC offset before FFT processing. Use Welch PSD with explicit window, segment length, overlap, and frequency range recorded in analysis JSON. Displayed plots must distinguish raw PSD from any smoothing used only for peak detection.

Alternative considered: single full-length FFT. Welch PSD is more stable for noisy accelerometer captures and repeated comparisons.

### Shaper evaluation

Implement Shake&Bake shaper candidate evaluation in analyzer code using independently written formulas and fixtures. Candidate names are `zv`, `mzv`, `ei`, `2hump_ei`, and `3hump_ei`. Output includes selected low-vibration and performance-oriented candidates only when residual vibration, smoothing, and acceleration estimates are finite and within configured bounds.

Alternative considered: import Klipper internal `shaper_calibrate.py`. Direct internal imports repeat the API-churn problem and make external analyzer behavior dependent on the user's installed Klipper tree.

### Damping estimate

Estimate dominant resonance damping with a half-power bandwidth method using PSD half-power (`peak / 2`) semantics. If the PSD shape does not support a valid half-power crossing, report damping as unavailable and continue with shaper evaluation defaults that are explicitly recorded.

Alternative considered: inherit observed `peak / sqrt(2)` PSD behavior from other tools. That equation applies to amplitude, not PSD power, and produces inconsistent damping estimates.

### Output files

Write these derived files:

- `analysis-shaper.json`: machine-readable validation, PSD metadata, peak list, candidates, selection, warnings, and capture fingerprint.
- `summary.txt` or `summary.md`: human-readable axis results and warnings.
- `input-shaper.proposed.cfg`: proposed `[input_shaper]` block when recommendations are valid.
- `graphs/`: one or more graph images for X/Y PSD and candidate summary.

Alternative considered: embed outputs in the capture artifact. Separate files preserve raw capture immutability.

## Risks / Trade-offs

- [Risk] Shaper formulas can be subtly wrong → Mitigation: add synthetic resonance fixtures with known peaks and candidate-selection expectations before tuning thresholds.
- [Risk] LIS2DW aliasing can mimic mechanical faults → Mitigation: report sample-rate and aliasing warnings and avoid recommendations when signal quality is insufficient.
- [Risk] Degenerate captures can produce `NaN` correlations or invalid PSD arrays → Mitigation: validate every numeric array before metrics and return explicit invalid states.
- [Risk] Plotting dependencies differ by workstation → Mitigation: keep JSON analysis output authoritative and make plotting failures distinct from analysis failures.
