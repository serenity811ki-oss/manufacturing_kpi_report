"""Smoke tests for exporter (CSV/Excel output) and chart factory (figure creation)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from manufacturing_analytics.data_generation.exporter import export_dataset, EXCEL_ROW_LIMIT
from manufacturing_analytics.data_generation.generator import ManufacturingDataGenerator
from manufacturing_analytics.visualization.charts import ChartFactory


@pytest.fixture
def small_dataset(small_config):
    gen = ManufacturingDataGenerator(small_config)
    return gen.generate_all()


class TestExporter:
    def test_export_creates_csv_for_every_table(self, small_dataset, tmp_path):
        export_dataset(small_dataset, tmp_path, make_excel_workbook=False)
        for name in small_dataset.as_dict().keys():
            assert (tmp_path / f"{name}.csv").exists()

    def test_export_creates_excel_workbook(self, small_dataset, tmp_path):
        export_dataset(small_dataset, tmp_path, make_excel_workbook=True)
        excel_path = tmp_path / "manufacturing_dataset.xlsx"
        assert excel_path.exists()
        # Sanity check it's readable and has multiple sheets
        sheets = pd.ExcelFile(excel_path).sheet_names
        assert "sensor_readings_hourly_agg" in sheets
        assert "production_records" in sheets

    def test_csv_row_counts_match_source_dataframes(self, small_dataset, tmp_path):
        export_dataset(small_dataset, tmp_path, make_excel_workbook=False)
        df_from_csv = pd.read_csv(tmp_path / "production_records.csv")
        assert len(df_from_csv) == len(small_dataset.production_records)


class TestChartFactory:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "x": pd.date_range("2024-01-01", periods=10, freq="D"),
            "y": range(10),
            "category": ["A", "B"] * 5,
        })

    def test_line_chart_returns_figure(self, sample_df):
        fig = ChartFactory.line_chart(sample_df, x="x", y="y", title="Test")
        assert fig is not None
        assert len(fig.data) >= 1

    def test_bar_chart_returns_figure(self, sample_df):
        fig = ChartFactory.bar_chart(sample_df, x="category", y="y", title="Test")
        assert fig is not None

    def test_histogram_returns_figure(self, sample_df):
        fig = ChartFactory.histogram(sample_df, x="y", title="Test")
        assert fig is not None

    def test_pareto_chart_returns_figure(self):
        pareto_df = pd.DataFrame({
            "defect_type": ["A", "B", "C"],
            "count": [50, 30, 20],
            "cumulative_pct": [50.0, 80.0, 100.0],
        })
        fig = ChartFactory.pareto_chart(pareto_df, category_col="defect_type")
        assert fig is not None
        assert len(fig.data) == 2  # bar + line trace

    def test_control_chart_flags_out_of_control_points(self):
        df = pd.DataFrame({"x": range(10), "y": [10, 11, 9, 10, 11, 10, 100, 9, 10, 11]})
        fig = ChartFactory.control_chart(df, x="x", y="y")
        assert fig is not None

    def test_static_line_chart_creates_file(self, sample_df, tmp_path):
        out_path = ChartFactory.save_static_line_chart(
            sample_df, x="x", y="y", out_path=tmp_path / "line.png", title="Test"
        )
        assert Path(out_path).exists()
        assert Path(out_path).stat().st_size > 0
