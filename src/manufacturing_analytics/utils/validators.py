"""
validators.py
==============
Validation utilities for pipeline configuration and input data integrity.

Provides:
- ConfigValidator: Checks required YAML sections and parameter ranges
- PipelineValidator: Validates data paths, formats, and schemas
- DataQualityValidator: Schema validation for input DataFrames
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigValidator:
    """Validates configuration file structure and parameter values."""

    REQUIRED_SECTIONS = {
        "generator": ["factories_count", "production_lines_per_factory", "machines_per_line"],
        "data_quality": ["outlier_z_threshold", "missing_value_strategy"],
        "kpi_targets": ["oee", "availability", "performance", "quality"],
    }

    PARAMETER_RANGES = {
        "outlier_z_threshold": (1.0, 5.0),
        "factories_count": (1, 100),
        "production_lines_per_factory": (1, 50),
        "machines_per_line": (1, 30),
    }

    @classmethod
    def validate(cls, config: dict[str, Any]) -> list[str]:
        """
        Validate configuration structure and parameter values.

        Parameters
        ----------
        config : dict
            Parsed configuration dictionary

        Returns
        -------
        list[str]
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required sections
        for section, required_keys in cls.REQUIRED_SECTIONS.items():
            if section not in config:
                errors.append(f"Missing required section: '{section}'")
            else:
                for key in required_keys:
                    if key not in config[section]:
                        errors.append(f"Missing required key: '{section}.{key}'")

        # Check parameter ranges
        for param, (min_val, max_val) in cls.PARAMETER_RANGES.items():
            for section in config.values():
                if isinstance(section, dict) and param in section:
                    val = section[param]
                    if not (min_val <= val <= max_val):
                        errors.append(
                            f"Parameter '{param}' = {val} outside valid range [{min_val}, {max_val}]"
                        )

        return errors


class PipelineValidator:
    """Validates pipeline paths and data availability."""

    @staticmethod
    def validate_paths(config: dict[str, Any]) -> list[str]:
        """
        Validate that required directories can be created or exist.

        Parameters
        ----------
        config : dict
            Configuration with paths

        Returns
        -------
        list[str]
            List of validation errors
        """
        errors = []
        paths_to_check = ["data_dir", "output_dir", "log_dir"]

        for path_key in paths_to_check:
            if path_key in config.get("paths", {}):
                path = Path(config["paths"][path_key])
                parent = path.parent
                if not parent.exists():
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        errors.append(f"Cannot create directory {parent}: {str(e)}")

        return errors

    @staticmethod
    def validate_raw_data(raw_dir: Path) -> list[str]:
        """
        Check if required raw data files exist.

        Parameters
        ----------
        raw_dir : Path
            Directory containing raw CSV files

        Returns
        -------
        list[str]
            List of validation errors
        """
        required_files = [
            "factories.csv",
            "production_lines.csv",
            "machines.csv",
            "operators.csv",
            "shifts.csv",
        ]

        errors = []
        if raw_dir.exists():
            available = {p.name for p in raw_dir.glob("*.csv")}
            for required in required_files:
                if required not in available:
                    errors.append(f"Missing raw data file: {required}")
        else:
            errors.append(f"Raw data directory does not exist: {raw_dir}")

        return errors


class DataQualityValidator:
    """Validates DataFrame structure and data quality."""

    @staticmethod
    def validate_schema(
        df: pd.DataFrame,
        table_name: str,
        required_columns: list[str] | None = None,
        dtype_checks: dict[str, str] | None = None,
    ) -> list[str]:
        """
        Validate DataFrame schema and dtypes.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to validate
        table_name : str
            Name of the table for error messages
        required_columns : list[str], optional
            Required column names
        dtype_checks : dict[str, str], optional
            Column name to expected dtype string

        Returns
        -------
        list[str]
            List of validation errors
        """
        errors = []

        if df is None or df.empty:
            errors.append(f"Table '{table_name}' is empty or None")
            return errors

        # Check required columns
        if required_columns:
            missing = set(required_columns) - set(df.columns)
            if missing:
                errors.append(
                    f"Table '{table_name}' missing columns: {', '.join(missing)}"
                )

        # Check dtypes
        if dtype_checks:
            for col, expected_dtype in dtype_checks.items():
                if col in df.columns:
                    actual = str(df[col].dtype)
                    if not actual.startswith(expected_dtype):
                        errors.append(
                            f"Column '{table_name}.{col}' has dtype {actual}, "
                            f"expected {expected_dtype}"
                        )

        return errors

    @staticmethod
    def validate_data_quality(
        df: pd.DataFrame,
        table_name: str,
        max_null_pct: float = 10.0,
        min_rows: int = 0,
    ) -> dict[str, Any]:
        """
        Check data quality metrics.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to analyze
        table_name : str
            Table name for reporting
        max_null_pct : float
            Maximum acceptable null percentage per column
        min_rows : int
            Minimum required rows

        Returns
        -------
        dict[str, Any]
            Quality metrics report
        """
        report = {
            "table_name": table_name,
            "row_count": len(df),
            "column_count": len(df.columns),
            "null_by_column": {},
            "warnings": [],
            "errors": [],
        }

        if len(df) < min_rows:
            report["errors"].append(
                f"Insufficient rows: {len(df)} < {min_rows} minimum"
            )

        for col in df.columns:
            null_pct = (df[col].isnull().sum() / len(df)) * 100
            report["null_by_column"][col] = null_pct

            if null_pct > max_null_pct:
                report["warnings"].append(
                    f"Column '{col}' has {null_pct:.1f}% null values "
                    f"(exceeds {max_null_pct}% threshold)"
                )

        return report


def run_pre_pipeline_validation(config: dict[str, Any], raw_dir: Path) -> bool:
    """
    Run all pre-pipeline validations.

    Parameters
    ----------
    config : dict
        Configuration dictionary
    raw_dir : Path
        Path to raw data directory

    Returns
    -------
    bool
        True if all validations pass, False otherwise
    """
    logger.info("Running pre-pipeline validations...")
    all_errors = []

    # Validate config
    config_errors = ConfigValidator.validate(config)
    if config_errors:
        logger.error("Configuration validation failed:")
        for err in config_errors:
            logger.error("  • {}", err)
        all_errors.extend(config_errors)

    # Validate paths
    path_errors = PipelineValidator.validate_paths(config)
    if path_errors:
        logger.error("Path validation failed:")
        for err in path_errors:
            logger.error("  • {}", err)
        all_errors.extend(path_errors)

    if all_errors:
        logger.error("Validation failed with {} errors", len(all_errors))
        return False

    logger.info("✓ All pre-pipeline validations passed")
    return True
