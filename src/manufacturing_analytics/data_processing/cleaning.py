"""
cleaning.py
===========
Data validation and cleaning pipeline for raw manufacturing tables.

Implements, in a single reusable class:
    * Automatic dtype conversion (dates, numerics, categoricals)
    * Missing-value handling (median / mean / drop / forward-fill)
    * Duplicate detection & removal (subset-key aware)
    * Outlier detection via z-score, with a "flag, don't silently drop"
      philosophy — outliers are marked in a boolean column so downstream
      KPI code can decide how to treat them.
    * A lightweight schema validation step that checks required columns
      and non-negative business constraints (e.g. units produced >= 0).

Every method returns a *new* DataFrame (no in-place mutation) and logs a
before/after summary, so the cleaning pipeline is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CleaningReport:
    """Summary of what the cleaning pipeline changed for one table."""

    table_name: str
    rows_before: int
    rows_after: int
    duplicates_removed: int = 0
    missing_values_filled: dict[str, int] = field(default_factory=dict)
    outliers_flagged: dict[str, int] = field(default_factory=dict)
    dtype_conversions: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"[{self.table_name}] rows {self.rows_before} -> {self.rows_after} "
            f"(-{self.duplicates_removed} dupes) | "
            f"missing filled: {self.missing_values_filled} | "
            f"outliers flagged: {self.outliers_flagged}"
        )


class DataCleaner:
    """Reusable, configurable cleaning pipeline for manufacturing tables."""

    def __init__(self, config: dict[str, Any]):
        """
        Parameters
        ----------
        config:
            Parsed ``config.yaml`` dict (uses the ``data_quality`` section).
        """
        self.cfg = config.get("data_quality", {})
        self.z_threshold = self.cfg.get("outlier_z_threshold", 3.0)
        self.missing_strategy = self.cfg.get("missing_value_strategy", "median")
        self.dedup_keys = self.cfg.get("duplicate_subset_keys", {})

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def clean(
        self,
        df: pd.DataFrame,
        table_name: str,
        date_cols: list[str] | None = None,
        numeric_cols: list[str] | None = None,
        category_cols: list[str] | None = None,
        outlier_cols: list[str] | None = None,
        non_negative_cols: list[str] | None = None,
    ) -> tuple[pd.DataFrame, CleaningReport]:
        """Run the full cleaning pipeline on a single table.

        Parameters
        ----------
        df: raw input DataFrame.
        table_name: logical name, used for logging and dedup-key lookup.
        date_cols: columns to coerce to datetime.
        numeric_cols: columns to coerce to numeric dtype.
        category_cols: columns to coerce to pandas 'category' dtype.
        outlier_cols: numeric columns to z-score and flag outliers on.
        non_negative_cols: columns whose values must be >= 0 (business rule).

        Returns
        -------
        (cleaned_df, report)
        """
        report = CleaningReport(table_name=table_name, rows_before=len(df), rows_after=len(df))
        out = df.copy()

        out, report = self._convert_dtypes(out, date_cols, numeric_cols, category_cols, report)
        out, report = self._remove_duplicates(out, table_name, report)
        out, report = self._handle_missing_values(out, numeric_cols or [], report)
        out, report = self._flag_outliers(out, outlier_cols or [], report)
        out = self._enforce_non_negative(out, non_negative_cols or [])

        report.rows_after = len(out)
        logger.info(report.summary())
        return out, report

    # ------------------------------------------------------------------ #
    # Step 1: dtype conversion
    # ------------------------------------------------------------------ #
    def _convert_dtypes(
        self,
        df: pd.DataFrame,
        date_cols: list[str] | None,
        numeric_cols: list[str] | None,
        category_cols: list[str] | None,
        report: CleaningReport,
    ) -> tuple[pd.DataFrame, CleaningReport]:
        for col in date_cols or []:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                report.dtype_conversions[col] = "datetime64"

        for col in numeric_cols or []:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                report.dtype_conversions[col] = "numeric"

        for col in category_cols or []:
            if col in df.columns:
                df[col] = df[col].astype("category")
                report.dtype_conversions[col] = "category"

        return df, report

    # ------------------------------------------------------------------ #
    # Step 2: duplicate removal
    # ------------------------------------------------------------------ #
    def _remove_duplicates(
        self, df: pd.DataFrame, table_name: str, report: CleaningReport
    ) -> tuple[pd.DataFrame, CleaningReport]:
        subset = self.dedup_keys.get(table_name)
        subset = [c for c in (subset or []) if c in df.columns] or None

        before = len(df)
        df = df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
        report.duplicates_removed = before - len(df)
        return df, report

    # ------------------------------------------------------------------ #
    # Step 3: missing value handling
    # ------------------------------------------------------------------ #
    def _handle_missing_values(
        self, df: pd.DataFrame, numeric_cols: list[str], report: CleaningReport
    ) -> tuple[pd.DataFrame, CleaningReport]:
        # Numeric columns: fill per configured strategy.
        for col in numeric_cols:
            if col not in df.columns:
                continue
            n_missing = int(df[col].isna().sum())
            if n_missing == 0:
                continue

            if self.missing_strategy == "median":
                fill_value = df[col].median()
                df[col] = df[col].fillna(fill_value)
            elif self.missing_strategy == "mean":
                fill_value = df[col].mean()
                df[col] = df[col].fillna(fill_value)
            elif self.missing_strategy == "ffill":
                df[col] = df[col].ffill().bfill()
            elif self.missing_strategy == "drop":
                df = df.dropna(subset=[col])
            report.missing_values_filled[col] = n_missing

        # Categorical / ID columns: fill with an explicit sentinel so
        # missingness is visible rather than silently dropped rows.
        object_cols = df.select_dtypes(include=["object", "string"]).columns
        for col in object_cols:
            n_missing = int(df[col].isna().sum())
            if n_missing > 0:
                df[col] = df[col].fillna("UNKNOWN")
                report.missing_values_filled[col] = n_missing

        return df, report

    # ------------------------------------------------------------------ #
    # Step 4: outlier detection (z-score) — flags, does not delete
    # ------------------------------------------------------------------ #
    def _flag_outliers(
        self, df: pd.DataFrame, outlier_cols: list[str], report: CleaningReport
    ) -> tuple[pd.DataFrame, CleaningReport]:
        for col in outlier_cols:
            if col not in df.columns or df[col].dropna().empty:
                continue
            values = df[col].astype(float)
            z_scores = np.abs(stats.zscore(values, nan_policy="omit"))
            flag_col = f"{col}_is_outlier"
            df[flag_col] = pd.Series(z_scores, index=df.index) > self.z_threshold
            df[flag_col] = df[flag_col].fillna(False)
            report.outliers_flagged[col] = int(df[flag_col].sum())
        return df, report

    # ------------------------------------------------------------------ #
    # Step 5: business-rule enforcement
    # ------------------------------------------------------------------ #
    @staticmethod
    def _enforce_non_negative(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        for col in cols:
            if col in df.columns:
                df[col] = df[col].clip(lower=0)
        return df

    # ------------------------------------------------------------------ #
    # Schema validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def validate_schema(df: pd.DataFrame, required_columns: list[str], table_name: str) -> bool:
        """Verify required columns are present. Logs and returns False if not."""
        missing = set(required_columns) - set(df.columns)
        if missing:
            logger.error("Table '{}' is missing required columns: {}", table_name, missing)
            return False
        logger.debug("Table '{}' passed schema validation.", table_name)
        return True
