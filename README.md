# 🏭 Manufacturing Analytics Platform

A production-ready Python platform for manufacturing data analysis — synthetic
data generation, data cleaning/validation, industrial KPI engineering (OEE,
MTBF, MTTR, scrap/defect rates, throughput, and more), interactive Plotly
dashboards, and automated Excel/PDF reporting.

Built as a reference implementation of how a professional data/analytics team
would structure a manufacturing analytics codebase: modular, tested,
configurable, logged, and documented.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Folder Structure](#folder-structure)
4. [Installation](#installation)
5. [Quick Start](#quick-start)
6. [Usage Examples](#usage-examples)
7. [Data Model](#data-model)
8. [KPI Reference](#kpi-reference)
9. [Sample Outputs](#sample-outputs)
10. [Testing](#testing)
11. [Configuration](#configuration)
12. [Troubleshooting](#troubleshooting)
13. [Architecture](#architecture)
14. [Future Improvements](#future-improvements)
15. [License](#license)

---

## Overview

This project simulates a realistic manufacturing operation — multiple
factories, production lines, machines, operators, shifts, downtime events,
quality inspections, defects, and IoT sensor readings — over **12+ months of
production history**, then runs that data through a full analytics pipeline:

```
GENERATE  →  CLEAN & VALIDATE  →  CALCULATE KPIs  →  VISUALIZE  →  REPORT
```

Everything is driven by a single YAML configuration file, logged with
Loguru, and covered by a PyTest suite — so the same codebase can just as
easily point at a real MES/historian export instead of synthetic data.

## Features

- ✅ **Synthetic data generation** — 3 factories, 7 production lines, 18
  machines, 100+ operators, 3 shifts, 12+ months of history, with realistic
  seasonality, machine "personality" (consistent performance/quality drift
  per machine), and intentionally injected data-quality issues (missing
  values, duplicates, outliers) so the cleaning pipeline has real work to do.
- ✅ **CSV + Excel export** for every table (large high-frequency sensor data
  is exported to CSV plus an hourly-aggregated Excel sheet, since Excel
  worksheets cap out at ~1,048,576 rows).
- ✅ **Data cleaning & validation** — automatic dtype conversion, configurable
  missing-value strategies, subset-aware duplicate removal, z-score outlier
  flagging, and business-rule enforcement (no negative units, etc.).
- ✅ **Industrial KPI engineering** — OEE (with its Availability / Performance
  / Quality components), MTBF, MTTR, scrap rate, defect rate, cycle time,
  utilization, throughput, first-pass yield, and Pareto analysis — using
  weighted aggregation (not naive mean-of-means).
- ✅ **Rich visualization** — line, bar, histogram, scatter, box, heatmap,
  Pareto, SPC control charts, and KPI gauges, in both interactive Plotly and
  static Matplotlib/Seaborn flavors.
- ✅ **Automated reporting** — a formatted, multi-sheet Excel workbook (RAG
  conditional formatting, frozen headers, autosized columns) and a polished
  PDF executive report with embedded charts.
- ✅ **Self-contained interactive HTML dashboard** — no server required.
- ✅ **Config-driven** — every parameter (factory count, shift patterns,
  sensor ranges, KPI targets, cleaning thresholds) lives in
  `config/config.yaml`.
- ✅ **Fully tested** — 50+ PyTest unit tests across generation, cleaning,
  KPI math, and validation framework.
- ✅ **Structured logging** via Loguru (console + rotating file) with debug mode.
- ✅ **Validation framework** — comprehensive config, path, and data quality
  validation with clear error messages.
- ✅ **Advanced CLI** — `--dry-run`, `--debug`, `--skip-report`, custom config support.
- ✅ **Modern dashboard UI** — professional design with gradients, animations,
  responsive layout, and status indicators.
- ✅ **Extensible architecture** — clear seams for ML, SQL, REST API,
  Streamlit, Power BI, Docker, and cloud deployment (see
  [Future Improvements](#future-improvements)).

## Folder Structure

```
manufacturing_analytics/
├── main.py                       # Pipeline entry point (generate→clean→KPI→viz→report)
├── requirements.txt
├── pyproject.toml                # Packaging + pytest/black/ruff config
├── README.md
├── config/
│   └── config.yaml               # Single source of truth for all parameters
├── src/
│   └── manufacturing_analytics/
│       ├── data_generation/      # Synthetic data generator + CSV/Excel exporter
│       ├── data_processing/      # Cleaning, validation, outlier detection
│       ├── kpi/                  # OEE, MTBF/MTTR, scrap/defect rate, Pareto
│       ├── visualization/        # Plotly + Matplotlib/Seaborn chart factory
│       ├── reporting/            # Excel (openpyxl) + PDF (fpdf2) report builders
│       ├── dashboards/           # Self-contained interactive HTML dashboard
│       └── utils/                # Config loader, Loguru logging setup
├── data/
│   ├── raw/                      # Generated CSV + combined Excel workbook
│   └── processed/                # Cleaned tables + computed KPI tables
├── dashboards/                   # Generated interactive HTML dashboard
├── reports/
│   ├── excel/                    # Generated Excel KPI report
│   └── pdf/                      # Generated PDF executive report
├── notebooks/
│   └── 01_exploratory_analysis.ipynb
├── tests/                        # PyTest suite (generation, cleaning, KPIs, charts)
└── docs/
    └── architecture.md           # Design decisions + extension roadmap
```

## Installation

**Requirements:** Python 3.12+

```bash
# 1. Clone / unzip the project, then cd into it
cd manufacturing_analytics

# 2. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Core libraries used

| Library | Purpose |
|---|---|
| pandas, numpy | Data manipulation & numerical computing |
| openpyxl, xlsxwriter | Excel read/write & formatting |
| scipy | Z-score outlier detection |
| scikit-learn | Reserved for the ML/predictive-maintenance roadmap |
| matplotlib, seaborn | Static charts for PDF reports |
| plotly | Interactive dashboard charts |
| kaleido | Static image export for Plotly (optional) |
| fpdf2 | Lightweight PDF report generation |
| jupyter | Exploratory analysis notebook |
| pytest, pytest-cov | Unit testing & coverage |
| loguru | Structured logging |
| PyYAML | Configuration file parsing |

## Quick Start

Run the entire pipeline end-to-end with one command:

```bash
python main.py
```

This will:
1. Generate a full synthetic dataset into `data/raw/` (CSV + Excel)
2. Clean/validate it and write results to `data/processed/`
3. Compute all KPIs and write KPI tables to `data/processed/`
4. Build the interactive dashboard at `dashboards/manufacturing_dashboard.html`
5. Build the Excel report at `reports/excel/manufacturing_kpi_report.xlsx`
   and the PDF report at `reports/pdf/manufacturing_kpi_report.pdf`

### CLI Options

| Option | Purpose | Example |
|--------|---------|---------|
| `--skip-generate` | Reuse existing raw data (skip generation) | `python main.py --skip-generate` |
| `--dry-run` | Validate config only (no processing) | `python main.py --dry-run` |
| `--debug` | Verbose debug logging | `python main.py --debug` |
| `--skip-report` | Build dashboard only (skip Excel/PDF) | `python main.py --skip-report` |
| `--config` | Custom config file path | `python main.py --config custom.yaml` |

### Quick Examples

```bash
# Full pipeline (default)
python main.py

# Reuse existing data, skip report generation
python main.py --skip-generate --skip-report

# Validate config before processing
python main.py --dry-run

# Verbose debugging
python main.py --debug

# Custom configuration
python main.py --config config/production.yaml
```

## Usage Examples

### Generate data programmatically

```python
from manufacturing_analytics.utils.config import load_config
from manufacturing_analytics.data_generation.generator import ManufacturingDataGenerator
from manufacturing_analytics.data_generation.exporter import export_dataset

config = load_config()
generator = ManufacturingDataGenerator(config)
dataset = generator.generate_all()

export_dataset(dataset, raw_dir="data/raw")
print(dataset.production_records.head())
```

### Clean a table

```python
from manufacturing_analytics.data_processing.cleaning import DataCleaner

cleaner = DataCleaner(config)
clean_df, report = cleaner.clean(
    dataset.production_records,
    table_name="production",
    date_cols=["date"],
    numeric_cols=["downtime_minutes", "total_units_produced"],
    outlier_cols=["downtime_minutes"],
    non_negative_cols=["total_units_produced"],
)
print(report.summary())
```

### Compute OEE and other KPIs

```python
from manufacturing_analytics.kpi.calculations import KPICalculator

kpi_calc = KPICalculator(config)
with_oee = kpi_calc.add_oee_components(clean_df)
factory_kpis = kpi_calc.aggregate_kpis(with_oee, group_by=["factory_id"])
print(factory_kpis[["factory_id", "oee", "availability", "performance", "quality"]])
```

### Build a chart and an interactive dashboard

```python
from manufacturing_analytics.visualization.charts import ChartFactory
from manufacturing_analytics.dashboards.plotly_dashboard import DashboardBuilder

cf = ChartFactory()
fig = cf.line_chart(factory_kpis, x="factory_id", y="oee", title="OEE by Factory")

dashboard = DashboardBuilder(title="Plant Overview")
dashboard.add_figure(fig)
dashboard.save("dashboards/my_dashboard.html")
```

### Build an Excel + PDF report

```python
from manufacturing_analytics.reporting.excel_report import ExcelReportBuilder
from manufacturing_analytics.reporting.pdf_report import PDFReportBuilder

excel = ExcelReportBuilder(kpi_targets=config["kpi_targets"])
excel.add_kpi_summary_sheet({"OEE": 0.81, "Availability": 0.94, "Quality": 0.97})
excel.add_dataframe_sheet(factory_kpis, "Factory KPIs", percent_cols=["oee"])
excel.save("reports/excel/my_report.xlsx")

pdf = PDFReportBuilder(title="My KPI Report")
pdf.add_page()
pdf.add_section_title("Summary")
pdf.add_paragraph("Overall OEE was 81% this period.")
pdf.save("reports/pdf/my_report.pdf")
```

## Data Model

| Table | Grain | Approx. rows (12 mo, default config) |
|---|---|---|
| `factories` | 1 row per factory | 3 |
| `production_lines` | 1 row per line | 7 |
| `machines` | 1 row per machine | 18 |
| `operators` | 1 row per operator | ~30 |
| `shifts` | 1 row per shift definition | 3 |
| `production_records` | machine × date × shift | ~16,000 |
| `downtime_events` | discrete stoppage event | ~20,000 |
| `quality_inspections` | inspection event | ~33,000 |
| `defects` | defective unit line-item | ~17,000 |
| `sensor_readings` | machine × timestamp × sensor type | ~390,000 |

Every fact table carries the foreign keys needed to roll up to any grain
(factory, line, machine, shift, month) without additional joins beyond the
dimension tables.

## KPI Reference

| KPI | Formula |
|---|---|
| **Availability** | Run Time ÷ Planned Production Time |
| **Performance**  | (Ideal Cycle Time × Total Units) ÷ Run Time |
| **Quality**       | Good Units ÷ Total Units Produced |
| **OEE**            | Availability × Performance × Quality |
| **MTBF**           | Total Uptime ÷ Number of Unplanned Failures |
| **MTTR**           | Total Unplanned Downtime ÷ Number of Unplanned Failures |
| **Scrap Rate**     | Scrap Units ÷ Total Units Produced |
| **Defect Rate**    | Defective Units ÷ Units Inspected |
| **Cycle Time (actual)** | Run Time ÷ Total Units Produced |
| **Utilization**    | Run Time ÷ Planned Production Time |
| **Throughput**     | Total Units Produced ÷ Run Time (per hour) |
| **First-Pass Yield** | Passed Inspections ÷ Total Inspections |

All rate/ratio KPIs are aggregated with **weighted averages** (weighted by
run time, planned time, or units produced as appropriate) rather than a
naive mean-of-means, which is one of the most common KPI-reporting mistakes.

## Sample Outputs

Running `python main.py` with the default configuration produces, from 12
months of data across 3 factories / 7 lines / 18 machines:

- **Monthly OEE trend**: ranges ~77%–86% with visible seasonality
- **Factory-level OEE**: all three factories land in the 81–82% range
- **MTBF/MTTR**: ~7–8 hours between unplanned failures, ~20 minutes average
  repair time per machine
- **Defect Pareto**: top 3 defect types account for ~35% of all defects
- A 4-page **PDF executive report** with KPI cards, trend/bar/box/Pareto
  charts, and a factory KPI table
- An 8-sheet **Excel workbook** (Cover, Executive Summary with RAG status,
  Monthly/Factory/Machine KPIs, MTBF & MTTR, Defect Rate, Pareto)
- A **modern interactive HTML dashboard** with:
  - 4 KPI metric cards with trend indicators
  - Monthly OEE trend chart (12-month history)
  - Factory-level OEE comparison
  - Shift-level analysis
  - Quality distribution analysis
  - **Pareto analysis** chart (80/20 defect breakdown)
  - Summary table with status badges (Good/Monitor/Bad)
  - Professional UI with gradients, animations, responsive design
  - Live timestamp and connection status

## Testing

```bash
pytest                          # run the full suite
pytest --cov                    # with coverage report
pytest tests/test_kpi.py -v     # run just the KPI tests
pytest tests/test_validators.py # test the validation framework
```

The suite (50+ tests) covers:
- **Dimension/fact table generation** — correctness and referential integrity
- **Data cleaning** — duplicate removal, missing-value handling, outlier flagging,
  dtype conversion, non-negative enforcement, schema validation
- **KPI math** — OEE formula correctness, edge cases (zero planned time),
  MTBF/MTTR, defect rate, Pareto ordering/cumulative percentage, weighted
  aggregation
- **Validation framework** — config validation, path validation, data quality checks
- **Exporter (CSV/Excel)** and **chart-factory** smoke tests

### Validation Framework

New validator classes in `utils/validators.py`:

```python
from manufacturing_analytics.utils.validators import (
    ConfigValidator,
    PipelineValidator,
    DataQualityValidator,
)

# Validate configuration structure and parameters
errors = ConfigValidator.validate(config)
if errors:
    for err in errors:
        print(f"Configuration error: {err}")

# Validate data quality
report = DataQualityValidator.validate_data_quality(
    df, table_name="production", max_null_pct=10.0
)
if report["warnings"]:
    for warning in report["warnings"]:
        print(f"Quality warning: {warning}")
```

## Configuration

All tunable parameters live in `config/config.yaml`: date range, factory/
line/machine counts, shift definitions, sensor normal ranges, downtime
reason codes, defect types, data-quality thresholds, and KPI targets (used
for Red/Amber/Green status coloring in dashboards and reports). Change the
YAML — no code edits needed — to regenerate a differently-shaped dataset.

### Validation

The configuration is automatically validated on startup:
- ✓ Required sections present (generator, data_quality, kpi_targets)
- ✓ Required parameters present in each section
- ✓ Parameter values within valid ranges
- ✓ Directories can be created with proper permissions

Run `python main.py --dry-run` to validate configuration before processing.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for design rationale,
data-flow diagrams (in text form), and the extension points built in for
the roadmap below.

## Troubleshooting

### Configuration Errors

If you see configuration validation errors, use dry-run mode to see detailed issues:

```bash
python main.py --dry-run
```

This will validate `config.yaml` and show specific errors without processing data.

### Data Quality Issues

Enable debug logging to see detailed cleaning steps and validation warnings:

```bash
python main.py --debug
```

This prints verbose information about missing values, outliers, and data transformations.

### Performance Problems

To measure stage-by-stage performance:

```bash
python main.py --debug 2>&1 | grep "seconds"
```

This shows timing for each pipeline stage.

### Development & Testing

Build dashboard without reports to speed up iteration:

```bash
python main.py --skip-generate --skip-report
```

Reuse existing data and skip slow report generation while developing.

## Architecture

## Future Improvements

The architecture leaves explicit seams for:

- 🤖 **Machine learning & predictive maintenance** — `scikit-learn` is
  already a dependency; `machines_clean.csv` + `sensor_readings` +
  `mtbf_mttr_machine.csv` are shaped for a failure-prediction model.
- 🔍 **AI-powered anomaly detection** — sensor readings already carry
  z-score outlier flags; the next step is an isolation-forest / autoencoder
  model in a new `anomaly_detection/` subpackage.
- 🗄️ **SQL integration** — swap `pandas.read_csv` for `SQLAlchemy` engine
  reads/writes; the dimensional model here maps directly to a star schema.
- 🌐 **REST API** — wrap `KPICalculator` and `ChartFactory` behind a
  FastAPI app so a frontend or BI tool can query KPIs live.
- 📊 **Streamlit dashboard** — every `ChartFactory` method returns a
  `plotly.graph_objects.Figure`, which drops directly into
  `st.plotly_chart(fig)` with no changes.
- 📈 **Power BI** — point Power BI at the `data/processed/*.csv` files or a
  future SQL backend for enterprise BI distribution.
- 🐳 **Docker** — containerize `main.py` plus a `Dockerfile`/
  `docker-compose.yml` for one-command reproducible runs.
- ☁️ **Cloud deployment** — the pipeline is stateless and config-driven,
  so it deploys cleanly to AWS Batch/Lambda, Azure Functions, or GCP Cloud
  Run with the raw/processed directories backed by S3/Blob/GCS.

## License

MIT License — see [`LICENSE`](LICENSE).
