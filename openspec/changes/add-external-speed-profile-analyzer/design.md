## Context

Speed-profile analysis runs outside Klipper against captures containing speed/direction measurements. For Max 4 CoreXY, acquisition measures 45 degree and 135 degree directions. The analyzer integrates vibration energy over frequency for each measurement and projects the measured motor-axis profiles over 0-360 degrees using CoreXY motor-speed decomposition.

Output is guidance, not an automatic slicer edit. Preferred speed ranges and avoid bands are vibration-based recommendations that require print validation.

## Goals / Non-Goals

**Goals:**

- Provide `shakeandbake analyze speed-profile <capture> --output-dir <dir>`.
- Validate speed grid, direction metadata, samples, sample rate, and PSD quality.
- Compute vibration energy per speed/direction measurement.
- Project CoreXY results across 0-360 degrees.
- Detect vibration peaks to avoid and low-energy valleys to prefer.
- Write JSON, summary, and graph outputs.

**Non-Goals:**

- No printer communication or data acquisition.
- No Klipper imports.
- No slicer profile edits.
- No Z-axis analysis.
- No claim that vibration guidance alone defines maximum printable speed.

## Decisions

### Energy metric

For each measurement, compute PSD and integrate energy over the configured frequency band. Record the frequency band, PSD method, and integration method in analysis JSON.

Alternative considered: use raw time-domain RMS only. Frequency-domain energy supports avoid-band and resonance interpretation.

### CoreXY projection

Use CoreXY motor-speed decomposition to combine 45 degree and 135 degree measured profiles into estimated vibration guidance over 0-360 degrees. Record the projection method and angular resolution in JSON.

Alternative considered: report only the two measured directions. Projection provides actionable speed/angle guidance while preserving measured data in outputs.

### Avoid and preferred ranges

Detect avoid bands around vibration-energy peaks and preferred ranges around low-energy valleys. Include configurable margins and minimum-width filters. Report uncertainty when data is sparse or noisy.

Alternative considered: return one best speed. A single speed hides direction dependence and measurement uncertainty.

### Output authority

JSON is authoritative. Graphs visualize speed-vs-angle heatmap, per-speed energy summaries, avoid bands, and preferred ranges. Plotting failure is reported separately from analysis failure.

Alternative considered: graph-only output. Machine-readable JSON supports regression tests and downstream tools.

## Risks / Trade-offs

- [Risk] Energy metrics are sensitive to sample quality and LIS2DW aliasing → Mitigation: validate PSDs and emit sample-rate, noise, and aliasing warnings.
- [Risk] Projection can overstate confidence between measured directions → Mitigation: record projection method and mark results as vibration guidance requiring print validation.
- [Risk] Large speed grids create large outputs → Mitigation: summarize per-speed and per-angle metrics while preserving detailed JSON arrays.
