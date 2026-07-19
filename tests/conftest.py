"""Shared pytest fixtures for the Manufacturing Analytics test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure `src/` is importable when running `pytest` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manufacturing_analytics.utils.config import load_config


@pytest.fixture(scope="session")
def config() -> dict:
    """Load the real project config (small, fast, deterministic seed)."""
    return load_config()


@pytest.fixture
def small_config(config) -> dict:
    """A cut-down copy of the config for fast test-time data generation."""
    cfg = {k: v for k, v in config.items()}
    cfg["data_generation"] = dict(config["data_generation"])
    cfg["data_generation"]["start_date"] = "2024-01-01"
    cfg["data_generation"]["months_of_history"] = 1
    cfg["data_generation"]["factories"] = [
        {"id": "F01", "name": "Test Plant", "country": "USA", "lines": 1}
    ]
    cfg["data_generation"]["machines_per_line"] = [1, 2]
    cfg["data_generation"]["operators_per_factory"] = [2, 3]
    return cfg


@pytest.fixture
def sample_production_df() -> pd.DataFrame:
    """A small, hand-crafted production_records DataFrame for KPI unit tests."""
    return pd.DataFrame({
        "record_id": ["PR001", "PR002", "PR003"],
        "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
        "shift_id": ["S1", "S2", "S1"],
        "factory_id": ["F01", "F01", "F02"],
        "line_id": ["F01-L1", "F01-L1", "F02-L1"],
        "machine_id": ["F01-L1-M1", "F01-L1-M1", "F02-L1-M1"],
        "planned_production_time_minutes": [480.0, 480.0, 480.0],
        "downtime_minutes": [30.0, 60.0, 0.0],
        "run_time_minutes": [450.0, 420.0, 480.0],
        "ideal_cycle_time_seconds": [30.0, 30.0, 20.0],
        "total_units_produced": [800, 700, 1400],
        "good_units": [780, 650, 1380],
        "scrap_units": [20, 50, 20],
    })


@pytest.fixture
def sample_downtime_df() -> pd.DataFrame:
    """A small hand-crafted downtime_events DataFrame."""
    return pd.DataFrame({
        "event_id": ["DT001", "DT002", "DT003"],
        "record_id": ["PR001", "PR002", "PR003"],
        "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
        "shift_id": ["S1", "S2", "S1"],
        "factory_id": ["F01", "F01", "F02"],
        "line_id": ["F01-L1", "F01-L1", "F02-L1"],
        "machine_id": ["F01-L1-M1", "F01-L1-M1", "F02-L1-M1"],
        "reason_code": ["Mechanical Failure", "Changeover / Setup", "Mechanical Failure"],
        "duration_minutes": [30.0, 60.0, 0.0],
        "is_planned": [False, True, False],
        "start_time": ["2024-01-01T07:00:00", "2024-01-01T15:00:00", "2024-01-02T07:00:00"],
    })


@pytest.fixture
def dirty_dataframe() -> pd.DataFrame:
    """A DataFrame containing missing values, duplicates, and an outlier for cleaning tests.

    Uses enough "normal" points (n=10) that a single extreme value produces a
    z-score that actually clears the outlier threshold — with very small
    samples, an outlier inflates its own standard deviation enough to mask
    itself (a well-known limitation of the z-score method).
    """
    normal_values = [9.8, 10.1, 9.9, 10.3, 10.0, 9.7, 10.2, 10.4, 9.6, 10.0,
                      9.9, 10.1, 10.0, 9.8, 10.2, 9.9, 10.1, 10.0, 9.7]
    values = normal_values + [np.nan, 50.0, 50.0]  # + missing, outlier, duplicate-of-outlier
    n = len(values)
    categories = [("A" if i % 2 == 0 else "B") for i in range(n)]
    categories[-3] = None  # missing category aligned with the missing value row
    df = pd.DataFrame({
        "id": list(range(1, n)) + [n - 1],  # duplicate final id (matches the duplicated value row)
        "value": values,
        "category": categories,
    })
    return df
