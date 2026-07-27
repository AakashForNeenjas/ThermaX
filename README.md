# ThermaX (Thermal Analyzer)

ThermaX is a Python package for analyzing thermal test data from Excel files for power electronics. It provides a CLI for batch analysis and report generation, plus a Streamlit dashboard for interactive exploration and reporting.

This README is a single, detailed documentation file covering the project goals, data flow, usage, and a file-by-file reference.

## What this project does

- Loads thermal test data from Excel (.xlsx) files.
- Normalizes time columns and extracts metadata from filenames.
- Computes statistics, limit checks, steady-state detection, and physics metrics.
- Generates plots, HTML reports, and Excel summaries.
- Provides both CLI and Streamlit UI workflows.

## Architecture at a glance (data flow)

```
Excel files (.xlsx)
  -> io.excel_loader.load_thermal_run
     -> ThermalRun (time + data + metadata)
        -> analysis (stats, limits, steady-state, physics)
        -> plots (matplotlib)
        -> reporting (HTML, Excel)
  -> UI (Streamlit) or CLI (argparse)
```

## Quick start

### 1. Create and use a virtual environment

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### 2. Install dependencies

For full CLI and UI features, install requirements plus the package:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -e .
```

Note: `setup.py` lists core analysis dependencies. `requirements.txt` includes Streamlit and Plotly for the dashboard.

## CLI usage

The CLI entrypoint is `thermal` (declared in `setup.py`).

Analyze a single run:

```bash
thermal analyze-run path\to\data.xlsx --components-config config/components.csv --output-dir out
```

Analyze an entire folder (campaign):

```bash
thermal analyze-folder path\to\folder --components-config config/components.csv --output-dir out
```

Compare one component across runs:

```bash
thermal compare-component "DAB(M12)" --folder path\to\folder --components-config config/components.csv --output-dir out
```

CLI outputs:
- Per-run plots and reports under `out\{run_id}\`.
- Campaign worst-case Excel under `out\campaign_worst_case.xlsx`.
- CSV exports for per-run stats/limits, campaign worst-case, and component comparisons.

## Streamlit dashboard

Run the dashboard (recommended command that does not require PowerShell script activation):

```powershell
& .\.venv\Scripts\python.exe -m streamlit run thermal_analyzer\ui\dashboard.py
```

Dashboard modes:
- Single Run Analysis: upload an Excel file, compute stats, limits, steady state, plots, and optional HTML report.
- Campaign Analysis: analyze a folder of runs and generate a campaign report.
- Component Comparison: compare one component across runs with plots and optional report.
- Samples Comparison (A vs B): match runs by metadata and compare temperature deltas.
- Configuration Editor: edit and save `config/components.csv` from the UI.
Download buttons are available for CSV exports (stats, limits, comparisons) where applicable.

## Input data format

Excel file requirements:
- Must contain a time column named `MCGS_TIME`.
- All other columns are treated as component temperature channels.
- Time values can be `HH:MM:SS`, `HH:MM:SS.sss`, or numeric seconds.

Filename metadata:
- `thermal_analyzer/utils/naming.py` extracts metadata from the filename, for example:
  - `255VAC_84VHV_6ALV_50Degree.xlsx`
  - Extracts `VAC`, `HV`, `LV_current`, `ambient_temp`

## Configuration file

`config/components.csv` defines component metadata and limits:

- `name_raw`: exact column name in the Excel file.
- `display_name`: friendly name for plots and reports.
- `group`: logical grouping (DAB, PFC, Magnetics, etc.).
- `max_limit`, `warning_limit`, `critical_limit`: temperature thresholds.
- `color_hint`: optional plotting color.

The loader (`thermal_analyzer/config.py`) strips whitespace and supports CSV or JSON.

## Outputs

Generated outputs are written to:
- `out/`: CLI run artifacts and comparisons (PNG, XLSX).
- `reports/`: HTML reports and report-related plots.
CSV exports are written alongside CLI outputs or offered as downloads in the dashboard.

These folders are safe to delete and regenerate. They are not required for the code to run.

## Testing

Run tests from the repo root:

```powershell
& .\.venv\Scripts\python.exe -m pytest
```

Tests cover:
- Correct time-above-threshold integration.
- Importability of the Streamlit dashboard and Streamlit availability.

## File-by-file reference

This section documents every file currently present in the project tree.

### Root

- `README.md`: This full project documentation.
- `requirements.txt`: Full dependency list, including Streamlit and Plotly for the UI.
- `setup.py`: Package metadata, install requirements for core analysis, and CLI entrypoint.

### Config

- `config/components.csv`: Component definitions and thermal limits used by analysis and UI.

### Sample data

- `samples/sample_run.csv`: Sample data for development or quick experiments (not wired to the loader directly, which expects Excel).

### Python package: `thermal_analyzer`

- `thermal_analyzer/__init__.py`: Package version (`__version__`).
- `thermal_analyzer/config.py`: Loads component configs from CSV/JSON into `ComponentConfig`.
- `thermal_analyzer/models.py`: Dataclasses for `ComponentConfig`, `ThermalRun`, and `TestCampaign`.

#### `thermal_analyzer/analysis`

- `thermal_analyzer/analysis/__init__.py`: Package marker.
- `thermal_analyzer/analysis/stats.py`: `compute_component_stats` (max/min/avg/std, max dT/dt, time to thresholds).
- `thermal_analyzer/analysis/thresholds.py`: `evaluate_limits`, including accurate time-above-threshold integration.
- `thermal_analyzer/analysis/steady_state.py`: `detect_steady_state` using slope over a time window.
- `thermal_analyzer/analysis/physics.py`: `compute_thermal_resistance` and `compute_time_constants`.
- `thermal_analyzer/analysis/comparisons.py`: Compare components across runs and compute worst-case combinations.
- `thermal_analyzer/analysis/matching.py`: Match runs from two campaigns by metadata signature.

#### `thermal_analyzer/io`

- `thermal_analyzer/io/__init__.py`: Package marker.
- `thermal_analyzer/io/excel_loader.py`: `load_thermal_run` to read Excel and normalize time.
- `thermal_analyzer/io/batch_loader.py`: `load_campaign_from_folder` to read a folder into `TestCampaign`.

#### `thermal_analyzer/plots`

- `thermal_analyzer/plots/__init__.py`: Package marker.
- `thermal_analyzer/plots/time_series.py`: Time-series plots with optional limit lines.
- `thermal_analyzer/plots/summary_plots.py`: Max temperature bar charts and cross-run comparison plots.

#### `thermal_analyzer/reporting`

- `thermal_analyzer/reporting/__init__.py`: Package marker.
- `thermal_analyzer/reporting/html_report.py`: HTML report per run with embedded plots and limit tables.
- `thermal_analyzer/reporting/generic_report.py`: Simple HTML report builder for arbitrary sections.
- `thermal_analyzer/reporting/excel_export.py`: Multi-sheet Excel report export.

#### `thermal_analyzer/ui`

- `thermal_analyzer/ui/__init__.py`: Package marker.
- `thermal_analyzer/ui/cli.py`: CLI entrypoint (`thermal`) with analyze and compare commands.
- `thermal_analyzer/ui/dashboard.py`: Streamlit UI for interactive analysis and reporting.

#### `thermal_analyzer/utils`

- `thermal_analyzer/utils/__init__.py`: Package marker.
- `thermal_analyzer/utils/file_utils.py`: File discovery and output directory helpers.
- `thermal_analyzer/utils/time_utils.py`: Time parsing utilities for `MCGS_TIME`.
- `thermal_analyzer/utils/naming.py`: Metadata extraction from filenames.

### Tests

- `tests/test_thresholds_time_above.py`: Verifies correct integration for time-above-threshold.
- `tests/test_dashboard_startup.py`: Ensures package and Streamlit dashboard module import.

### Generated artifacts (not core source)

These files are generated by running the software or Python itself. They can be deleted and re-created.

- `out/compare_DAB(M12).png`: Example comparison plot from CLI.
- `out/compare_DAB(M12).xlsx`: Example comparison data from CLI.
- `out/campaign_worst_case.xlsx`: Example campaign summary.
- `reports/comp_AUX Tx 1 winding_report.html`: Example component report.
- `reports/comp_AUX Tx 1 winding.png`: Example component plot.
- `reports/campaign_report.html`: Example campaign report.
- `reports/campaign_overview.png`: Example campaign plot.
- `reports/210VAC_104VHV_6VLV_50Degree_ts.png`: Example time-series plot.
- `reports/210VAC_104VHV_6VLV_50Degree_report.html`: Example single-run report.
- `reports/210VAC_104VHV_6VLV_50Degree_bar.png`: Example bar plot.

### Package metadata and caches (generated)

- `thermal_analyzer.egg-info/PKG-INFO`: Built package metadata.
- `thermal_analyzer.egg-info/SOURCES.txt`: File list recorded by packaging tools.
- `thermal_analyzer.egg-info/requires.txt`: Dependencies captured at build time.
- `thermal_analyzer.egg-info/entry_points.txt`: Console entrypoints.
- `thermal_analyzer.egg-info/dependency_links.txt`: Packaging metadata.
- `thermal_analyzer.egg-info/top_level.txt`: Top-level package name.
- `tests/__pycache__/test_thresholds_time_above.cpython-314-pytest-9.0.2.pyc`: Bytecode cache.
- `tests/__pycache__/test_dashboard_startup.cpython-314-pytest-9.0.2.pyc`: Bytecode cache.
- `thermal_analyzer/**/__pycache__/*.pyc`: Bytecode caches for each module.

### Environment artifacts

- `.venv/`: Local virtual environment (contains interpreter and site-packages).
- `.pytest_cache/`: Pytest cache directory.

If you want a shorter README plus a separate, formal reference manual, I can split this into two files. For now, everything is kept in this single README as requested.
