## ADDED Requirements

### Requirement: External Belt Analyzer CLI
The system SHALL provide an external CLI command for CoreXY A/B belt-path analysis.

#### Scenario: Analyze valid belt capture
- **WHEN** `shakeandbake analyze belts <capture-file> --output-dir <dir>` is run with valid A and B measurement blocks
- **THEN** the analyzer writes belt-analysis outputs under the selected output directory

#### Scenario: Analyzer does not contact printer
- **WHEN** belt analysis runs
- **THEN** it does not issue Klipper commands, connect to the printer, or modify printer configuration

### Requirement: A/B Capture Validation
The system SHALL validate paired A and B measurement blocks before comparison.

#### Scenario: Missing path blocks comparison
- **WHEN** the capture lacks a valid A or B measurement block
- **THEN** the analyzer records `missing_path` diagnostics and does not compute belt similarity metrics

#### Scenario: Invalid samples block comparison
- **WHEN** either path has nonmonotonic time, non-finite samples, insufficient samples, or constant signal
- **THEN** the analyzer records validation diagnostics and does not compute belt similarity metrics

### Requirement: PSD Validation
The system SHALL validate PSD arrays before comparison metrics are computed.

#### Scenario: Degenerate PSD is rejected
- **WHEN** either PSD array is empty, constant, all zero, or non-finite
- **THEN** the analyzer records `invalid_psd` and omits comparison metrics requiring that PSD

### Requirement: Peak Detection and Pairing
The system SHALL detect and pair A/B resonance peaks on a common frequency grid.

#### Scenario: Peaks are paired by frequency proximity
- **WHEN** A and B peaks fall within the configured pairing threshold
- **THEN** the analyzer records paired peaks with path frequencies, frequency delta, and amplitude ratio

#### Scenario: Peaks remain unpaired
- **WHEN** A or B peaks have no match within the pairing threshold
- **THEN** the analyzer records unpaired peaks and includes a warning in the summary

### Requirement: Multi-Metric Belt Comparison
The system SHALL compute multiple comparison metrics when inputs are valid.

#### Scenario: Valid comparison metrics are available
- **WHEN** A and B PSD arrays are finite, nonempty, and nonconstant
- **THEN** the analyzer records normalized area difference, paired-peak deltas, paired-peak amplitude ratios, and correlation

#### Scenario: Correlation is invalid
- **WHEN** correlation cannot be computed because PSD arrays are constant or non-finite
- **THEN** the analyzer marks correlation unavailable and does not emit `NaN`

### Requirement: Output Files
The system SHALL write belt analysis outputs separately from the raw capture.

#### Scenario: Analysis output is written
- **WHEN** belt analysis completes with valid or diagnostic output
- **THEN** the analyzer writes `analysis-belts.json`, a human-readable summary, and graph files when graph generation succeeds

#### Scenario: Source capture is referenced
- **WHEN** any belt-analysis output is written
- **THEN** it references the source capture path or fingerprint

### Requirement: Motor Metadata Reporting
The system SHALL report QIDI closed-loop X/Y motor metadata when capture metadata includes it.

#### Scenario: Metadata is available
- **WHEN** capture metadata includes closed-loop X/Y current or microstep fields
- **THEN** the belt-analysis JSON and summary include those fields as contextual annotations
