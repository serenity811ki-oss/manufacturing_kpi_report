"""
exporter.py
===========
Persists a :class:`GeneratedDataset` to disk as CSV and Excel files.

Design decision — why sensor_readings is CSV-only
---------------------------------------------------
Excel worksheets are capped at 1,048,576 rows. With 12+ months of
15-minute-interval readings across every machine and sensor type, the raw
``sensor_readings`` table can exceed that ceiling. Real-world plants keep
raw historian data in CSV/Parquet/a time-series database and only bring
*aggregated* sensor data into Excel for human review — this exporter
mirrors that pattern:

* ``sensor_readings.csv``            -> full-resolution raw data (CSV only)
* ``sensor_readings_hourly.xlsx``    -> hourly mean/min/max aggregation (Excel-safe)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from manufacturing_analytics.data_generation.generator import GeneratedDataset
from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)

EXCEL_ROW_LIMIT = 1_048_576 - 10  # small safety margin below Excel's hard cap


def export_dataset(
    dataset: GeneratedDataset,
    raw_dir: str | Path,
    make_excel_workbook: bool = True,
) -> None:
    """Write every table in ``dataset`` to CSV, and (optionally) a combined
    multi-sheet Excel workbook for tables that fit within Excel's row limit.

    Parameters
    ----------
    dataset:
        The generated dataset container.
    raw_dir:
        Output directory for raw data files (created if missing).
    make_excel_workbook:
        If True, also produce ``manufacturing_dataset.xlsx`` with one sheet
        per table (tables too large for a single sheet are aggregated).
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    tables = dataset.as_dict()

    # --- 1. CSV: always written, one file per table (safe for any size) ---
    for name, df in tables.items():
        csv_path = raw_dir / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        logger.info("Wrote {} rows -> {}", len(df), csv_path)

    if not make_excel_workbook:
        return

    # --- 2. Excel: one workbook, one sheet per table (or its aggregate) ---
    excel_path = raw_dir / "manufacturing_dataset.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for name, df in tables.items():
            if name == "sensor_readings":
                sheet_df = _aggregate_sensor_readings_hourly(df)
                sheet_name = "sensor_readings_hourly_agg"
            else:
                sheet_df = df
                sheet_name = name

            if len(sheet_df) > EXCEL_ROW_LIMIT:
                logger.warning(
                    "Table '{}' has {} rows, exceeding Excel's limit — truncating "
                    "to the most recent {} rows for the workbook (full data remains in CSV).",
                    name, len(sheet_df), EXCEL_ROW_LIMIT,
                )
                sheet_df = sheet_df.tail(EXCEL_ROW_LIMIT)

            sheet_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            logger.info("Excel sheet '{}': {} rows written.", sheet_name[:31], len(sheet_df))

    logger.success("Excel workbook written -> {}", excel_path)


def _aggregate_sensor_readings_hourly(sensor_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw sensor readings to hourly mean/min/max per machine/sensor.

    This keeps the Excel export small and human-readable while the full
    resolution data remains available in ``sensor_readings.csv``.
    """
    if sensor_df.empty:
        return sensor_df

    df = sensor_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.floor("h")

    agg = (
        df.groupby(["machine_id", "factory_id", "line_id", "sensor_type", "hour"])["reading_value"]
        .agg(mean_value="mean", min_value="min", max_value="max", n_readings="count")
        .reset_index()
        .sort_values(["machine_id", "sensor_type", "hour"])
    )
    return agg
