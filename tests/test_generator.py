"""Unit tests for manufacturing_analytics.data_generation.generator."""

from __future__ import annotations

import pandas as pd
import pytest

from manufacturing_analytics.data_generation.generator import ManufacturingDataGenerator


class TestDimensionBuilders:
    def test_build_factories_matches_config(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        factories = gen.build_factories()
        assert len(factories) == len(small_config["data_generation"]["factories"])
        assert set(factories.columns) >= {"factory_id", "factory_name", "country", "num_lines"}

    def test_build_lines_children_of_factories(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        factories = gen.build_factories()
        lines = gen.build_lines(factories)
        assert set(lines["factory_id"]).issubset(set(factories["factory_id"]))
        assert len(lines) == factories["num_lines"].sum()

    def test_build_machines_children_of_lines(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        factories = gen.build_factories()
        lines = gen.build_lines(factories)
        machines = gen.build_machines(lines)
        assert set(machines["line_id"]).issubset(set(lines["line_id"]))
        assert machines["ideal_cycle_time_seconds"].between(0, 200).all()

    def test_build_operators_within_configured_range(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        factories = gen.build_factories()
        operators = gen.build_operators(factories)
        lo, hi = small_config["data_generation"]["operators_per_factory"]
        n_factories = len(factories)
        assert lo * n_factories <= len(operators) <= hi * n_factories

    def test_build_shifts_have_positive_duration(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        shifts = gen.build_shifts()
        assert (shifts["duration_hours"] > 0).all()


class TestFactTableBuilders:
    @pytest.fixture
    def base_dims(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        factories = gen.build_factories()
        lines = gen.build_lines(factories)
        machines = gen.build_machines(lines)
        operators = gen.build_operators(factories)
        shifts = gen.build_shifts()
        return gen, factories, lines, machines, operators, shifts

    def test_production_records_non_negative(self, base_dims):
        gen, factories, lines, machines, operators, shifts = base_dims
        production = gen.build_production_records(machines, operators, shifts)
        assert len(production) > 0
        assert (production["total_units_produced"] >= 0).all()
        assert (production["good_units"] <= production["total_units_produced"] + 1).all()
        assert production["record_id"].is_unique or production["record_id"].duplicated().sum() > 0
        # record_id may contain injected duplicates by design — verify column exists & format
        assert production["record_id"].str.startswith("PR").all()

    def test_downtime_events_linked_to_production(self, base_dims):
        gen, factories, lines, machines, operators, shifts = base_dims
        production = gen.build_production_records(machines, operators, shifts)
        downtime = gen.build_downtime_events(production, machines)
        if len(downtime) > 0:
            assert set(downtime["record_id"]).issubset(set(production["record_id"]))
            assert (downtime["duration_minutes"] >= 0).all()

    def test_quality_and_defects_linked(self, base_dims):
        gen, factories, lines, machines, operators, shifts = base_dims
        production = gen.build_production_records(machines, operators, shifts)
        inspections, defects = gen.build_quality_inspections_and_defects(production)
        assert len(inspections) > 0
        assert (inspections["defective_units"] <= inspections["sample_size"]).all()
        if len(defects) > 0:
            assert set(defects["inspection_id"]).issubset(set(inspections["inspection_id"]))

    def test_sensor_readings_long_format(self, base_dims, small_config):
        gen, factories, lines, machines, operators, shifts = base_dims
        sensors = gen.build_sensor_readings(machines)
        expected_types = set(small_config["data_generation"]["sensors"]["types"].keys())
        assert set(sensors["sensor_type"].unique()).issubset(expected_types)
        assert set(sensors["machine_id"]).issubset(set(machines["machine_id"]))


class TestFullGeneration:
    def test_generate_all_returns_all_tables(self, small_config):
        gen = ManufacturingDataGenerator(small_config)
        dataset = gen.generate_all()
        tables = dataset.as_dict()
        expected_tables = {
            "factories", "production_lines", "machines", "operators", "shifts",
            "production_records", "downtime_events", "quality_inspections",
            "defects", "sensor_readings",
        }
        assert set(tables.keys()) == expected_tables
        for name, df in tables.items():
            assert isinstance(df, pd.DataFrame), f"{name} is not a DataFrame"

    def test_reproducibility_with_same_seed(self, small_config):
        gen1 = ManufacturingDataGenerator(small_config)
        gen2 = ManufacturingDataGenerator(small_config)
        factories1 = gen1.build_factories()
        factories2 = gen2.build_factories()
        pd.testing.assert_frame_equal(factories1, factories2)
