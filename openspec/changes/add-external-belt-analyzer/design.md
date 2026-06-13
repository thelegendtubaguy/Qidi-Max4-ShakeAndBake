## Context

Belt-path analysis runs outside Klipper against paired CoreXY A/B capture artifacts. A valid input contains A direction `(1, -1, 0)` and B direction `(1, 1, 0)` measurement blocks captured with matched sweep parameters. The analyzer compares vibration response shapes and resonance peaks to help identify belt-path asymmetry or mechanical issues.

LIS2DW captures can be noisy or alias-prone, so the analyzer must validate inputs and report uncertainty. A single similarity number is not authoritative; output must include component metrics and diagnostics.

## Goals / Non-Goals

**Goals:**

- Provide `shakeandbake analyze belts <capture> --output-dir <dir>`.
- Validate A and B measurement blocks and PSD arrays before comparison.
- Compute PSD summaries, peak lists, paired peaks, unpaired peaks, area difference, amplitude ratios, and correlation when valid.
- Emit analysis JSON, a human-readable summary, and graph files.
- Include QIDI closed-loop X/Y motor-current metadata when available.

**Non-Goals:**

- No printer communication or data acquisition.
- No Klipper imports.
- No automatic config writes.
- No Z-axis analysis.
- No single metric presented as conclusive mechanical truth.

## Decisions

### Multi-metric comparison

Use multiple comparison metrics: paired-peak frequency delta, paired-peak amplitude ratio, normalized area difference, and Pearson correlation only when both PSD arrays are finite and nonconstant. Report invalid correlation as unavailable rather than numeric fallback.

Alternative considered: use only correlation. Correlation fails on constant or degenerate arrays and hides peak-level asymmetry.

### Peak pairing

Interpolate both PSDs onto a common frequency grid, detect peaks with relative and absolute thresholds, and pair peaks by frequency proximity using a bounded dynamic threshold. Unpaired peaks remain in the output and contribute to warnings.

Alternative considered: pair only the largest peaks. Single-peak pairing misses secondary resonance differences that matter mechanically.

### Diagnostic states

Use explicit statuses for `missing_path`, `invalid_capture`, `invalid_psd`, `insufficient_signal`, `unpaired_peaks`, `excessive_peak_count`, and `comparison_valid`. The JSON output records status per path and for the combined comparison.

Alternative considered: return 0% on invalid data. A numeric invalid fallback would be misleading.

### Graph layout

Generate independent Shake&Bake graph layouts for A/B PSD overlay and peak pairing. Graph generation failure must not corrupt JSON analysis output.

Alternative considered: make plotting required for success. JSON is the authoritative output and supports headless use.

## Risks / Trade-offs

- [Risk] LIS2DW aliasing can produce false peak differences → Mitigation: include sample-rate and aliasing warnings and require repeat capture language in summaries.
- [Risk] High peak counts can make pairing unstable → Mitigation: report excessive peak-count warning and keep all paired/unpaired peaks visible in JSON.
- [Risk] Correlation can produce non-finite results → Mitigation: validate arrays and mark correlation unavailable when invalid.
