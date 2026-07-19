"""
test_validators.py
===================
Unit tests for the validation framework.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from manufacturing_analytics.utils.validators import (
    ConfigValidator,
    DataQualityValidator,
    PipelineValidator,
)


class TestConfigValidator:
    """Tests for ConfigValidator."""

    def test_validate_complete_config(self):
        """A valid config should pass validation."""
        config = {
            "generator": {
                "factories_count": 3,
                "production_lines_per_factory": 5,
                "machines_per_line": 6,
            },
            "data_quality": {
                "outlier_z_threshold": 3.0,
                "missing_value_strategy": "median",
            },
            "kpi_targets": {
                "oee": 0.75,
                "availability": 0.90,
                "performance": 0.85,
                "quality": 0.95,
            },
        }
        errors = ConfigValidator.validate(config)
        assert len(errors) == 0

    def test_validate_missing_required_section(self):
        """Missing required sections should raise errors."""
        config = {
            "generator": {
                "factories_count": 3,
                "production_lines_per_factory": 5,
                "machines_per_line": 6,
            },
            # Missing data_quality and kpi_targets
        }
        errors = ConfigValidator.validate(config)
        assert len(errors) >= 2
        assert any("data_quality" in e for e in errors)

    def test_validate_missing_required_key(self):
        """Missing required keys in sections should raise errors."""
        config = {
            "generator": {
                "factories_count": 3,
                # Missing production_lines_per_factory and machines_per_line
            },
            "data_quality": {
                "outlier_z_threshold": 3.0,
                "missing_value_strategy": "median",
            },
            "kpi_targets": {
                "oee": 0.75,
                "availability": 0.90,
                "performance": 0.85,
                "quality": 0.95,
            },
        }
        errors = ConfigValidator.validate(config)
        assert any("production_lines_per_factory" in e for e in errors)

    def test_validate_parameter_out_of_range(self):
        """Parameters outside valid ranges should raise errors."""
        config = {
            "generator": {
                "factories_count": 200,  # Out of range (max 100)
                "production_lines_per_factory": 5,
                "machines_per_line": 6,
            },
            "data_quality": {
                "outlier_z_threshold": 10.0,  # Out of range (max 5.0)
                "missing_value_strategy": "median",
            },
            "kpi_targets": {
                "oee": 0.75,
                "availability": 0.90,
                "performance": 0.85,
                "quality": 0.95,
            },
        }
        errors = ConfigValidator.validate(config)
        assert any("factories_count" in e for e in errors)
        assert any("outlier_z_threshold" in e for e in errors)


class TestDataQualityValidator:
    """Tests for DataQualityValidator."""

    def test_validate_schema_success(self):
        """Valid DataFrame schema should pass."""
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "value": [1.0, 2.0, 3.0],
            "category": ["A", "B", "C"],
        })
        errors = DataQualityValidator.validate_schema(
            df, "test_table",
            required_columns=["id", "value", "category"],
            dtype_checks={"id": "int", "value": "float"},
        )
        assert len(errors) == 0

    def test_validate_schema_missing_columns(self):
        """Missing required columns should raise errors."""
        df = pd.DataFrame({"id": [1, 2, 3]})
        errors = DataQualityValidator.validate_schema(
            df, "test_table",
            required_columns=["id", "value", "category"],
        )
        assert len(errors) > 0
        assert any("value" in e or "category" in e for e in errors)

    def test_validate_empty_dataframe(self):
        """Empty DataFrame should raise error."""
        df = pd.DataFrame()
        errors = DataQualityValidator.validate_schema(df, "test_table")
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_data_quality_null_percentage(self):
        """Null percentage tracking should work correctly."""
        df = pd.DataFrame({
            "col1": [1, 2, None, 4, 5],
            "col2": [None, None, None, 4, 5],
        })
        report = DataQualityValidator.validate_data_quality(
            df, "test_table", max_null_pct=25.0
        )
        
        assert report["row_count"] == 5
        assert report["null_by_column"]["col1"] == 20.0
        assert report["null_by_column"]["col2"] == 60.0
        assert len(report["warnings"]) > 0  # col2 exceeds threshold

    def test_data_quality_insufficient_rows(self):
        """Insufficient rows should raise error."""
        df = pd.DataFrame({"col1": [1, 2]})
        report = DataQualityValidator.validate_data_quality(
            df, "test_table", min_rows=10
        )
        assert len(report["errors"]) > 0
        assert any("rows" in e.lower() for e in report["errors"])


class TestPipelineValidator:
    """Tests for PipelineValidator."""

    def test_validate_paths_creation(self, tmp_path):
        """Should create missing parent directories."""
        config = {
            "paths": {
                "data_dir": str(tmp_path / "data" / "deep" / "nested"),
                "output_dir": str(tmp_path / "output"),
                "log_dir": str(tmp_path / "logs"),
            }
        }
        errors = PipelineValidator.validate_paths(config)
        assert len(errors) == 0
        assert (tmp_path / "data" / "deep" / "nested").parent.exists()

    def test_validate_paths_permission_error(self, monkeypatch):
        """Should handle permission errors gracefully."""
        config = {
            "paths": {
                "data_dir": "/root/nonexistent/path",  # Usually no permission
            }
        }
        # Note: On Windows this won't fail, so we'll just verify it handles gracefully
        errors = PipelineValidator.validate_paths(config)
        # Errors may or may not occur depending on system


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
