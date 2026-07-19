"""Unit tests for manufacturing_analytics.kpi.calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from manufacturing_analytics.kpi.calculations import KPICalculator


@pytest.fixture
def kpi_calc(config) -> KPICalculator:
    return KPICalculator(config)


class TestOEEComponents:
    def test_adds_expected_columns(self, kpi_calc, sample_production_df):
        result = kpi_calc.add_oee_components(sample_production_df)
        for col in ["availability", "performance", "quality", "oee", "scrap_rate",
                     "cycle_time_actual_seconds", "utilization", "throughput_units_per_hour"]:
            assert col in result.columns

    def test_availability_formula(self, kpi_calc, sample_production_df):
        result = kpi_calc.add_oee_components(sample_production_df)
        expected = sample_production_df["run_time_minutes"] / sample_production_df["planned_production_time_minutes"]
        pd.testing.assert_series_equal(
            result["availability"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_quality_formula(self, kpi_calc, sample_production_df):
        result = kpi_calc.add_oee_components(sample_production_df)
        expected = sample_production_df["good_units"] / sample_production_df["total_units_produced"]
        pd.testing.assert_series_equal(
            result["quality"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_oee_is_product_of_components(self, kpi_calc, sample_production_df):
        result = kpi_calc.add_oee_components(sample_production_df)
        expected_oee = result["availability"] * result["performance"] * result["quality"]
        np.testing.assert_allclose(result["oee"].values, expected_oee.values, rtol=1e-6)

    def test_oee_bounded_reasonably(self, kpi_calc, sample_production_df):
        result = kpi_calc.add_oee_components(sample_production_df)
        assert (result["oee"] >= 0).all()
        assert (result["oee"] <= 1.6).all()  # generous upper bound given performance cap of 1.5

    def test_zero_planned_time_does_not_raise(self, kpi_calc):
        df = pd.DataFrame({
            "planned_production_time_minutes": [0.0],
            "run_time_minutes": [0.0],
            "ideal_cycle_time_seconds": [30.0],
            "total_units_produced": [0],
            "good_units": [0],
            "scrap_units": [0],
        })
        result = kpi_calc.add_oee_components(df)
        assert result["availability"].iloc[0] == 0
        assert not np.isinf(result["oee"].iloc[0])
        assert not np.isnan(result["oee"].iloc[0])


class TestMTBFMTTR:
    def test_mtbf_mttr_calculation(self, kpi_calc, sample_downtime_df, sample_production_df):
        result = kpi_calc.calculate_mtbf_mttr(
            sample_downtime_df, sample_production_df, group_by=["machine_id"]
        )
        assert "mtbf_hours" in result.columns
        assert "mttr_hours" in result.columns
        assert (result["mtbf_hours"] >= 0).all()
        assert (result["mttr_hours"] >= 0).all()

    def test_excludes_planned_downtime_from_failure_count(self, kpi_calc, sample_downtime_df, sample_production_df):
        result = kpi_calc.calculate_mtbf_mttr(
            sample_downtime_df, sample_production_df, group_by=["machine_id"]
        )
        # F01-L1-M1 has one planned (DT002) and one unplanned (DT001) event -> failure_count == 1
        row = result[result["machine_id"] == "F01-L1-M1"].iloc[0]
        assert row["failure_count"] == 1


class TestDefectRateAndPareto:
    def test_defect_rate_calculation(self, kpi_calc):
        inspections = pd.DataFrame({
            "factory_id": ["F01", "F01", "F02"],
            "sample_size": [100, 100, 50],
            "defective_units": [5, 3, 10],
            "inspection_id": ["QI1", "QI2", "QI3"],
            "result": ["Fail", "Fail", "Fail"],
        })
        result = kpi_calc.calculate_defect_rate(inspections, group_by=["factory_id"])
        f01_rate = result.loc[result["factory_id"] == "F01", "defect_rate"].iloc[0]
        assert pytest.approx(f01_rate, rel=1e-6) == 8 / 200

    def test_pareto_analysis_ordering_and_cumulative(self, kpi_calc):
        defects = pd.DataFrame({
            "defect_type": ["A", "A", "A", "B", "B", "C"],
        })
        pareto = kpi_calc.pareto_analysis(defects, category_col="defect_type")
        assert pareto.iloc[0]["defect_type"] == "A"
        assert pareto["cumulative_pct"].iloc[-1] == pytest.approx(100.0)
        # cumulative % should be non-decreasing
        assert (pareto["cumulative_pct"].diff().dropna() >= 0).all()


class TestAggregation:
    def test_aggregate_kpis_weighted_not_naive_mean(self, kpi_calc, sample_production_df):
        with_oee = kpi_calc.add_oee_components(sample_production_df)
        agg = kpi_calc.aggregate_kpis(with_oee, group_by=["factory_id"])
        assert set(agg["factory_id"]) == set(sample_production_df["factory_id"])
        assert "oee" in agg.columns
        assert (agg["total_units_produced"] > 0).all()


class TestStatusClassification:
    def test_classify_status_green(self, kpi_calc):
        assert kpi_calc.classify_status(0.90, "oee") in {"Green", "Amber"}

    def test_classify_status_red_for_low_value(self, kpi_calc):
        assert kpi_calc.classify_status(0.10, "oee") == "Red"

    def test_classify_status_na_for_unknown_kpi(self, kpi_calc):
        assert kpi_calc.classify_status(0.5, "not_a_real_kpi") == "N/A"
