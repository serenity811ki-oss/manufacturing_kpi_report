# Architecture & Design Notes

## 1. Design Principles

1. **Config over code.** Every parameter that could plausibly change between
   deployments (factory count, shift patterns, sensor thresholds, KPI
   targets, cleaning strategy) lives in `config/config.yaml`, not hard-coded
   constants. This means the same codebase can generate a small demo dataset
   or a much larger enterprise-scale one by editing YAML alone.

2. **Pure functions over stateful pipelines.** Every KPI/cleaning/chart
   function takes a DataFrame in and returns a DataFrame (or Figure) out. No
   hidden global state, no in-place mutation of caller-owned data. This is
   what makes the 45-test PyTest suite possible without a database or
   fixtures beyond plain DataFrames.

3. **Flag, don't silently discard.** Outlier detection marks rows with a
   boolean `<column>_is_outlier` flag rather than deleting them. Real
   manufacturing analysts often *want* to see the outlier (it might be a
   genuine, important stoppage) — the cleaning pipeline's job is to make
   data quality visible and auditable, not to make decisions for the user.

4. **Realistic-but-imperfect synthetic data.** The generator deliberately
   injects missing values, duplicate rows, and anomalous sensor spikes so
   the downstream cleaning/validation code is exercised in the same way it
   would be against a real MES export. A "perfectly clean" synthetic
   dataset would make `DataCleaner` a decoration rather than a tested
   component.

5. **Weighted aggregation, not mean-of-means.** `KPICalculator.aggregate_kpis`
   weights availability by planned time, performance by run time, and
   quality by units produced — not a naive `.mean()` across rows. A common
   real-world KPI bug is averaging daily OEE percentages without weighting
   by production volume, which silently over-weights low-volume/idle
   periods.

## 2. Data Flow

```
config/config.yaml
        │
        ▼
ManufacturingDataGenerator.generate_all()
        │  (factories → lines → machines → operators → shifts)
        │  (production_records → downtime_events)
        │  (quality_inspections → defects)
        │  (sensor_readings, vectorized with NumPy)
        ▼
export_dataset()  ──────────────► data/raw/*.csv + manufacturing_dataset.xlsx
        │
        ▼
DataCleaner.clean()  (per table: dtype conversion → dedupe → missing values
        │              → outlier flagging → non-negative enforcement)
        ▼
data/processed/*_clean.csv
        │
        ▼
KPICalculator
   .add_oee_components()      → row-level availability/performance/quality/OEE
   .aggregate_kpis()          → monthly / factory / machine / shift rollups
   .calculate_mtbf_mttr()     → reliability metrics from downtime_events
   .calculate_defect_rate()   → quality metrics from quality_inspections
   .pareto_analysis()         → defect Pareto table
        │
        ▼
data/processed/{monthly,factory,machine,shift}_kpis.csv, pareto.csv, ...
        │
        ├──► ChartFactory (Plotly)  → DashboardBuilder → dashboards/*.html
        │
        └──► ChartFactory (Matplotlib/Seaborn, PNG)
                     │
                     ▼
             ExcelReportBuilder → reports/excel/*.xlsx
             PDFReportBuilder   → reports/pdf/*.pdf
```

## 3. Why Sensor Data Is Handled Differently

Excel worksheets are hard-capped at 1,048,576 rows. Fifteen-minute (or
even hourly) sensor readings across a full machine fleet over a year
routinely exceeds that. Rather than silently truncating data or producing
an Excel file that fails to open, the platform:

- Always writes the **full-resolution** `sensor_readings.csv` (CSV has no
  row limit).
- Writes an **hourly mean/min/max aggregation** into the combined Excel
  workbook (`sensor_readings_hourly_agg` sheet), which is what a human
  reviewer actually wants to browse in a spreadsheet.

This mirrors how real plants operate: raw historian/IoT data lives in a
time-series database or data lake; only aggregated views make it into
Excel-based reporting.

## 4. Extension Points (Roadmap Seams)

| Roadmap item | Where it plugs in |
|---|---|
| ML / predictive maintenance | New `src/manufacturing_analytics/ml/` subpackage consuming `machines_clean.csv`, `sensor_readings.csv`, and `mtbf_mttr_machine.csv`; `scikit-learn` is already a listed dependency. |
| AI anomaly detection | Extend `DataCleaner._flag_outliers` (currently z-score) with an `IsolationForest`/autoencoder-based flag column, same DataFrame-in/DataFrame-out contract. |
| SQL integration | Replace `pandas.read_csv`/`to_csv` in `exporter.py` and `main.py` with `SQLAlchemy` engine calls — the dimensional model (factories → lines → machines; production_records as the central fact table) maps directly onto a star schema. |
| REST API | A FastAPI app in `src/manufacturing_analytics/api/` importing `KPICalculator` directly — no business logic needs to move, only a thin HTTP layer wraps it. |
| Streamlit dashboard | Every `ChartFactory` method returns a `plotly.graph_objects.Figure`; a Streamlit app can call `st.plotly_chart(fig)` on the exact same objects used by `DashboardBuilder`. |
| Power BI | Point Power BI's CSV/SQL connector at `data/processed/` or the future SQL backend. |
| Docker | Containerize `main.py` with a `Dockerfile` (base `python:3.12-slim`, `pip install -r requirements.txt`, `CMD ["python", "main.py"]`) plus a `docker-compose.yml` if a database is added. |
| Cloud deployment | The pipeline is stateless per run and config-driven, so `data/raw` and `data/processed` can be backed by S3/Blob/GCS with no code changes beyond path resolution. |

## 5. Testing Strategy

- **Generator tests** verify referential integrity (every `line_id` in
  `machines` exists in `production_lines`, etc.) and that generated values
  respect configured ranges — not just "does it run without throwing."
- **Cleaning tests** use a small hand-crafted "dirty" DataFrame with known
  missing values, duplicates, and one deliberately extreme outlier (with
  enough normal samples that z-scoring isn't masked by its own outlier —
  a real statistical property of the z-score method worth knowing about).
- **KPI tests** verify exact formula correctness against hand-computed
  expected values, plus edge cases (division by zero planned time).
- All tests run against a **cut-down config fixture** (`small_config`) so
  the full suite completes in under two seconds, while `main.py` itself
  exercises the full-scale default configuration.
