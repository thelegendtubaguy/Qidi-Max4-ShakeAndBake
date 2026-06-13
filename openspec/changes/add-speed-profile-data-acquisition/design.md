## Context

Speed-profile acquisition measures vibration response across speed steps and CoreXY movement directions. On Max 4, the command uses the main CoreXY directions 45 degrees and 135 degrees. The external analyzer projects those motor-axis measurements over 0-360 degrees and computes speed ranges to prefer or avoid.

The Max 4 host is constrained, so the printer-side command must only perform motion and capture. Heavy PSD integration, heatmap generation, and graphing run externally.

## Goals / Non-Goals

**Goals:**

- Register `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE`.
- Generate a bounded speed grid from command parameters.
- Capture raw accelerometer samples for 45 degree and 135 degree CoreXY directions at each speed.
- Use shorter movement segments at low speed and repeated motion at higher speed as encoded by the acquisition planner.
- Write all measurements into one versioned raw capture artifact.
- Restore input-shaper and velocity-limit state through cleanup paths.

**Non-Goals:**

- No vibration-energy integration, heatmap projection, avoid-band detection, or graphing in Klipper.
- No Z-axis speed profiling.
- No slicer profile edits.
- No non-CoreXY printer support.

## Decisions

### Direction set

Use 45 degrees and 135 degrees as the measured CoreXY main directions. Store direction angle, unit vector, and speed in every measurement block.

Alternative considered: directly measure every angle. Full angular sweeps are slower and less appropriate for the constrained host.

### Speed grid

Construct speeds from a positive lower bound through `MAX_SPEED` using `SPEED_INCREMENT`. Reject nonpositive increments and speed requests that exceed configured printer limits or preflight envelope checks.

Alternative considered: accept arbitrary speed lists. A generated grid is simpler to validate and reproduce.

### Duration management

The acquisition planner may use shorter segment lengths at low speeds and more repetitions as speed increases. The planned behavior must be recorded in metadata so external analysis understands sample duration and movement pattern per measurement.

Alternative considered: fixed segment length for every speed. Fixed long segments make low-speed captures unnecessarily slow.

### Analysis boundary

The command writes raw data only. It does not integrate PSD energy, project 0-360 degree heatmaps, detect avoid bands, or recommend slicer speeds.

Alternative considered: compute speed metrics during acquisition. The calculation is CPU-heavy and belongs outside Klipper.

## Risks / Trade-offs

- [Risk] Long speed-profile captures stress the Max 4 host → Mitigation: preflight reports resource warnings and the command avoids analysis and plotting.
- [Risk] Speed grid can create excessive measurement count → Mitigation: parameter validation enforces bounded speed count and reports the planned measurement count before motion.
- [Risk] Movement envelope can exceed bounds at high speed or long segments → Mitigation: validate the complete planned envelope before acquisition.
