# Shake&Bake

Shake&Bake captures QIDI Max 4 resonance, belt, and speed-limit evidence from Klipper, then analyzes the raw captures outside the printer process.

The printer-side Klipper extra writes immutable `.sbcapture.json` files. The external analyzer writes derived JSON, summaries, SVG graphs, and proposed config snippets without modifying `printer.cfg`.

## Target

- QIDI Max 4
- CoreXY X/Y motion
- Stock toolhead LIS2DW accelerometer
- Python 3

Z-axis resonance, shaper calibration, belt diagnostics, and speed profiling are intentionally unsupported.

## Install the Klipper extra on the printer

Copy the Klipper extra and its lightweight support packages into the Klipper source tree on the printer:

```sh
# Run from this repository on your workstation.
PRINTER=printer-hostname-or-ip
KLIPPER=/home/qidi/klipper

rsync -a klippy/extras/shakeandbake.py "$PRINTER:$KLIPPER/klippy/extras/"
rsync -a shakeandbake_capture shakeandbake_max4 "$PRINTER:$KLIPPER/klippy/"
```

Add the extra to `printer.cfg`:

```ini
[shakeandbake]
```

Restart Klipper after copying the files and updating `printer.cfg`.

## Install the external analyzer

Run the analyzer from a workstation or another environment outside Klipper:

```sh
git clone <repo-url> shakeandbake
cd shakeandbake
python3 -m venv .venv
. .venv/bin/activate
export PYTHONPATH="$PWD"
python -m shakeandbake_analyze --help
```

Optional `shakeandbake` wrapper:

```sh
mkdir -p ~/.local/bin
cat > ~/.local/bin/shakeandbake <<EOF
#!/usr/bin/env sh
PYTHONPATH="$(pwd)\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m shakeandbake_analyze "\$@"
EOF
chmod +x ~/.local/bin/shakeandbake
```

## Capture data on the printer

Run commands from the Klipper console or a connected UI. Use an absolute writable `OUTPUT_DIR` when possible.

Preflight:

```gcode
SHAKEANDBAKE_PREFLIGHT
```

X/Y input-shaper capture:

```gcode
SHAKEANDBAKE_CAPTURE_SHAPER AXIS=ALL OUTPUT_DIR=/tmp/shakeandbake-captures
# Default sweep: FREQ_START=5 FREQ_END=133 HZ_PER_SEC=1
```

CoreXY A/B belt-path capture:

```gcode
SHAKEANDBAKE_CAPTURE_BELTS OUTPUT_DIR=/tmp/shakeandbake-captures
```

Speed-limit evidence capture:

```gcode
SHAKEANDBAKE_CAPTURE_SPEED_LIMITS MAX_SPEED=300 SPEED_INCREMENT=100 ACCEL_MIN=5000 ACCEL_MAX=15000 ACCEL_INCREMENT=5000 OUTPUT_DIR=/tmp/shakeandbake-captures
```

Copy captures from the printer:

```sh
mkdir -p captures
scp 'printer-hostname-or-ip:/tmp/shakeandbake-captures/*.sbcapture.json' captures/
```

## Analyze captures

Activate the analyzer environment and run one analyzer per capture type.

Shaper analysis:

```sh
python -m shakeandbake_analyze analyze shaper captures/shaper-x-y-YYYYMMDDTHHMMSSZ.sbcapture.json --output-dir out/shaper
```

Belt analysis:

```sh
python -m shakeandbake_analyze analyze belts captures/belts-a-b-YYYYMMDDTHHMMSSZ.sbcapture.json --output-dir out/belts
```

Speed-limit analysis:

```sh
python -m shakeandbake_analyze analyze speed-limits captures/speed-limits-YYYYMMDDTHHMMSSZ.sbcapture.json --output-dir out/speed-limits
```

Useful options:

```sh
--json-only
--no-graphs
```

Analyzer outputs include:

- `analysis-shaper.json`, `analysis-belts.json`, or `analysis-speed-limits.json`
- `summary.txt` unless `--json-only` is used
- `graphs/*.svg` unless graph output is disabled
- `input-shaper.proposed.cfg` for shaper recommendations
- `speed-limits.proposed.cfg` and `slicer-motion-speed.proposed.txt` for speed-limit recommendations

Apply proposed config snippets manually after reviewing the generated files.

## Development checks

```sh
python3 -m unittest discover -s tests -v
```
