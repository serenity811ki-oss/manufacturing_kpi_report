"""Unit tests for manufacturing_analytics.data_processing.cleaning."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from manufacturing_analytics.data_processing.cleaning import DataCleaner


@pytest.fixture
def cleaner(config) -> DataCleaner:
    return DataCleaner(config)


class TestDuplicateRemoval:
    def test_removes_exact_duplicates(self, cleaner, dirty_dataframe):
        cleaned, report = cleaner.clean(dirty_dataframe, table_name="unknown_table")
        # No dedup_keys configured for "unknown_table" -> falls back to full-row dedupe
        assert report.rows_after <= report.rows_before

    def test_removes_duplicates_by_subset_key(self, config, sample_production_df):
        # Duplicate one row on the configured production dedup key
        df = pd.concat([sample_production_df, sample_production_df.iloc[[0]]], ignore_index=True)
        cleaner = DataCleaner(config)
        cleaned, report = cleaner.clean(
            df, table_name="production",
            numeric_cols=["total_units_produced"],
        )
        assert report.duplicates_removed >= 1
        assert len(cleaned) == len(sample_production_df)


class TestMissingValueHandling:
    def test_fills_numeric_missing_with_median(self, cleaner, dirty_dataframe):
        cleaned, report = cleaner.clean(dirty_dataframe, "unknown_table", numeric_cols=["value"])
        assert cleaned["value"].isna().sum() == 0
        assert "value" in report.missing_values_filled

    def test_fills_categorical_missing_with_unknown_sentinel(self, cleaner, dirty_dataframe):
        cleaned, _ = cleaner.clean(dirty_dataframe, "unknown_table", numeric_cols=["value"])
        assert (cleaned["category"] == "UNKNOWN").any()
        assert cleaned["category"].isna().sum() == 0


class TestOutlierDetection:
    def test_flags_extreme_values(self, cleaner, dirty_dataframe):
        cleaned, report = cleaner.clean(
            dirty_dataframe, "unknown_table", numeric_cols=["value"], outlier_cols=["value"]
        )
        assert "value_is_outlier" in cleaned.columns
        # The injected 50.0 values are far outside the ~9.6-10.4 normal range and should be flagged
        assert cleaned.loc[cleaned["value"] == 50.0, "value_is_outlier"].any()

    def test_outliers_are_flagged_not_dropped(self, cleaner, dirty_dataframe):
        rows_before = len(dirty_dataframe)
        cleaned, report = cleaner.clean(
            dirty_dataframe, "unknown_table", numeric_cols=["value"], outlier_cols=["value"]
        )
        # Duplicates get removed but outliers themselves should remain present (flagged only)
        assert report.rows_after >= rows_before - 1  # only the exact duplicate row is removed


class TestDtypeConversion:
    def test_converts_date_columns(self, cleaner, sample_production_df):
        cleaned, report = cleaner.clean(sample_production_df, "production", date_cols=["date"])
        assert pd.api.types.is_datetime64_any_dtype(cleaned["date"])

    def test_converts_numeric_columns_with_coercion(self, cleaner):
        df = pd.DataFrame({"amount": ["10", "20", "not_a_number"]})
        cleaned, report = cleaner.clean(df, "unknown_table", numeric_cols=["amount"])
        assert pd.api.types.is_numeric_dtype(cleaned["amount"])
        # "not_a_number" -> NaN -> filled by median strategy
        assert cleaned["amount"].isna().sum() == 0


class TestNonNegativeEnforcement:
    def test_clips_negative_values_to_zero(self, cleaner):
        df = pd.DataFrame({"units": [-5, 10, -1, 20]})
        cleaned, _ = cleaner.clean(df, "unknown_table", numeric_cols=["units"], non_negative_cols=["units"])
        assert (cleaned["units"] >= 0).all()


class TestSchemaValidation:
    def test_validate_schema_passes_with_all_columns(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        assert DataCleaner.validate_schema(df, ["a", "b"], "test_table") is True

    def test_validate_schema_fails_with_missing_columns(self):
        df = pd.DataFrame({"a": [1]})
        assert DataCleaner.validate_schema(df, ["a", "b"], "test_table") is False
