## ADDED Requirements

### Requirement: External Speed Profile CLI
The system SHALL provide an external CLI command for Max 4 CoreXY speed-profile analysis.

#### Scenario: Analyze valid speed-profile capture
- **WHEN** `shakeandbake analyze speed-profile <capture-file> --output-dir <dir>` is run with valid speed/direction measurements
- **THEN** the analyzer writes speed-profile outputs under the selected output directory

#### Scenario: Analyzer does not contact printer
- **WHEN** speed-profile analysis runs
- **THEN** it does not issue Klipper commands, connect to the printer, modify slicer profiles, or modify printer configuration

### Requirement: Speed Profile Validation
The system SHALL validate speed-profile capture data before analysis.

#### Scenario: Complete measurement grid is valid
- **WHEN** the capture contains valid 45 degree and 135 degree measurement blocks for each expected speed
- **THEN** the analyzer proceeds with PSD-energy analysis

#### Scenario: Incomplete measurement grid is diagnostic
- **WHEN** a speed or required direction is missing
- **THEN** the analyzer records a diagnostic and marks affected projected results unavailable

#### Scenario: Invalid samples block affected measurements
- **WHEN** a measurement has nonmonotonic time, non-finite samples, insufficient samples, constant signal, or unusable sample rate
- **THEN** the analyzer records measurement diagnostics and excludes that measurement from derived speed-profile metrics

### Requirement: Vibration Energy Computation
The system SHALL compute vibration energy per valid speed/direction measurement.

#### Scenario: PSD energy is computed
- **WHEN** a measurement has valid samples and PSD data
- **THEN** the analyzer records PSD metadata, frequency band, integrated energy, and sample-rate estimate for that measurement

### Requirement: CoreXY Angular Projection
The system SHALL project measured CoreXY speed-profile data over 0-360 degrees.

#### Scenario: Projection is available
- **WHEN** both required measured directions have valid energy data for a speed
- **THEN** the analyzer records projected vibration energy by angle for that speed

#### Scenario: Projection is unavailable
- **WHEN** required direction data is missing or invalid for a speed
- **THEN** projected angle data for that speed is marked unavailable with diagnostics

### Requirement: Avoid and Preferred Speed Ranges
The system SHALL identify vibration speed ranges to avoid and prefer when data quality supports it.

#### Scenario: Avoid bands are detected
- **WHEN** vibration-energy peaks exceed configured thresholds
- **THEN** the analyzer records avoid bands with speed range, peak speed, energy value, and margin

#### Scenario: Preferred ranges are detected
- **WHEN** low-energy valleys satisfy configured width and energy thresholds
- **THEN** the analyzer records preferred speed ranges with speed bounds and supporting energy metrics

### Requirement: Output Files
The system SHALL write speed-profile outputs separately from raw captures.

#### Scenario: Analysis output is written
- **WHEN** speed-profile analysis completes with valid or diagnostic output
- **THEN** the analyzer writes `analysis-speed-profile.json`, a human-readable summary, and graph files when graph generation succeeds

#### Scenario: Output references source capture
- **WHEN** any speed-profile output is written
- **THEN** it references the source capture path or fingerprint

### Requirement: Z-Axis Exclusion
The system SHALL NOT process Max 4 Z-axis movement as speed-profile input.

#### Scenario: Z-labeled measurements exist
- **WHEN** a capture includes Z-labeled measurements
- **THEN** the analyzer ignores them and records that Max 4 speed-profile analysis supports CoreXY X/Y directions only
