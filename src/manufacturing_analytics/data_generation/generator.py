"""
generator.py
============
Synthetic manufacturing data generator.

Produces a relationally-consistent set of dimension and fact tables that
mimic a real Manufacturing Execution System (MES) / historian export:

Dimension tables
    * factories, production_lines, machines, operators, shifts

Fact tables
    * production_records   (one row per machine / date / shift)
    * downtime_events       (irregular events tied to a production record)
    * quality_inspections   (1..N inspections per production record)
    * defects                (defect line-items linked to failed inspections)
    * sensor_readings        (high-frequency IoT-style time series per machine)

Design notes
------------
* All randomness is seeded (``config.data_generation.random_seed``) so
  generated datasets are reproducible across runs and machines.
* Values are intentionally noisy and imperfect (missing values, occasional
  duplicates, and some out-of-range readings) to give the downstream
  cleaning/validation pipeline real work to do — mirroring real-world MES
  exports, which are rarely pristine.
* Sensor data is deliberately high-frequency and therefore large; it is
  exported to CSV only (Excel's 1,048,576-row-per-sheet ceiling makes it
  impractical for a raw dump). An aggregated hourly/daily summary is
  produced separately for Excel consumption.
"""

from __future__ import annotations

import itertools
import random
import string
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GeneratedDataset:
    """Container holding every table produced by the generator."""

    factories: pd.DataFrame
    production_lines: pd.DataFrame
    machines: pd.DataFrame
    operators: pd.DataFrame
    shifts: pd.DataFrame
    production_records: pd.DataFrame
    downtime_events: pd.DataFrame
    quality_inspections: pd.DataFrame
    defects: pd.DataFrame
    sensor_readings: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        """Return all tables as a name -> DataFrame mapping for iteration."""
        return {
            "factories": self.factories,
            "production_lines": self.production_lines,
            "machines": self.machines,
            "operators": self.operators,
            "shifts": self.shifts,
            "production_records": self.production_records,
            "downtime_events": self.downtime_events,
            "quality_inspections": self.quality_inspections,
            "defects": self.defects,
            "sensor_readings": self.sensor_readings,
        }


class ManufacturingDataGenerator:
    """Generates a full synthetic manufacturing dataset from a config dict."""

    def __init__(self, config: dict[str, Any]):
        """
        Parameters
        ----------
        config:
            Parsed ``config.yaml`` dictionary (top-level, i.e. contains a
            ``data_generation`` key).
        """
        self.cfg = config["data_generation"]
        self.seed = self.cfg.get("random_seed", 42)
        self.rng = np.random.default_rng(self.seed)
        random.seed(self.seed)

        self.start_date = datetime.strptime(self.cfg["start_date"], "%Y-%m-%d").date()
        self.months = self.cfg["months_of_history"]
        self.end_date = self._add_months(self.start_date, self.months)

        logger.info(
            "Initialized generator: {} -> {} ({} months), seed={}",
            self.start_date, self.end_date, self.months, self.seed,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _add_months(start: date, months: int) -> date:
        """Add a number of calendar months to a date."""
        month = start.month - 1 + months
        year = start.year + month // 12
        month = month % 12 + 1
        day = min(start.day, 28)
        return date(year, month, day)

    def _date_range(self) -> list[date]:
        n_days = (self.end_date - self.start_date).days
        return [self.start_date + timedelta(days=i) for i in range(n_days)]

    @staticmethod
    def _random_string(prefix: str, n: int, width: int = 3) -> list[str]:
        return [f"{prefix}{str(i).zfill(width)}" for i in range(1, n + 1)]

    def _first_names(self) -> list[str]:
        return [
            "James", "Maria", "Wei", "Fatima", "Carlos", "Anna", "Liam", "Priya",
            "Kenji", "Sofia", "Ahmed", "Olga", "Diego", "Grace", "Noah", "Elena",
            "Marek", "Ingrid", "Tomasz", "Lucia", "Hassan", "Julia", "Piotr", "Nina",
        ]

    def _last_names(self) -> list[str]:
        return [
            "Smith", "Garcia", "Chen", "Khan", "Rodriguez", "Kowalski", "Novak",
            "Silva", "Muller", "Tanaka", "Nowak", "Wisniewski", "Torres", "Kim",
            "Ali", "Costa", "Becker", "Zielinski", "Santos", "Adamski",
        ]

    # ------------------------------------------------------------------ #
    # Dimension builders
    # ------------------------------------------------------------------ #
    def build_factories(self) -> pd.DataFrame:
        """Build the factories dimension table."""
        rows = [
            {
                "factory_id": f["id"],
                "factory_name": f["name"],
                "country": f["country"],
                "num_lines": f["lines"],
                "timezone": "UTC",
            }
            for f in self.cfg["factories"]
        ]
        df = pd.DataFrame(rows)
        logger.info("Generated {} factories.", len(df))
        return df

    def build_lines(self, factories: pd.DataFrame) -> pd.DataFrame:
        """Build the production_lines dimension table (children of factories)."""
        rows = []
        product_families = ["Widget-A", "Widget-B", "Bracket-X", "Housing-Y", "Gear-Z", "Panel-Q"]
        for _, f in factories.iterrows():
            for i in range(1, f["num_lines"] + 1):
                line_id = f"{f['factory_id']}-L{i}"
                rows.append({
                    "line_id": line_id,
                    "factory_id": f["factory_id"],
                    "line_name": f"Line {i}",
                    "product_family": random.choice(product_families),
                    "installed_year": random.randint(2012, 2022),
                })
        df = pd.DataFrame(rows)
        logger.info("Generated {} production lines.", len(df))
        return df

    def build_machines(self, lines: pd.DataFrame) -> pd.DataFrame:
        """Build the machines dimension table (children of production lines)."""
        machine_types = [
            "CNC Mill", "Injection Molder", "Robotic Welder", "Press Brake",
            "Assembly Robot", "Conveyor/Packaging Unit", "CNC Lathe", "Laser Cutter",
        ]
        lo, hi = self.cfg["machines_per_line"]
        cyc_lo, cyc_hi = self.cfg["target_cycle_time_seconds"]
        rows = []
        for _, ln in lines.iterrows():
            n_machines = random.randint(lo, hi)
            for i in range(1, n_machines + 1):
                machine_id = f"{ln['line_id']}-M{i}"
                rows.append({
                    "machine_id": machine_id,
                    "line_id": ln["line_id"],
                    "factory_id": ln["factory_id"],
                    "machine_name": f"{random.choice(machine_types)} {i}",
                    "machine_type": random.choice(machine_types),
                    "manufacturer": random.choice(["Siemens", "FANUC", "ABB", "Haas", "KUKA", "Mazak"]),
                    "install_date": (
                        self.start_date - timedelta(days=random.randint(200, 3000))
                    ).isoformat(),
                    "ideal_cycle_time_seconds": round(random.uniform(cyc_lo, cyc_hi), 1),
                    "nominal_capacity_units_per_hour": round(3600 / random.uniform(cyc_lo, cyc_hi), 1),
                })
        df = pd.DataFrame(rows)
        logger.info("Generated {} machines.", len(df))
        return df

    def build_operators(self, factories: pd.DataFrame) -> pd.DataFrame:
        """Build the operators dimension table."""
        lo, hi = self.cfg["operators_per_factory"]
        first, last = self._first_names(), self._last_names()
        rows = []
        op_counter = 1
        for _, f in factories.iterrows():
            n_ops = random.randint(lo, hi)
            for _ in range(n_ops):
                operator_id = f"OP{str(op_counter).zfill(4)}"
                op_counter += 1
                rows.append({
                    "operator_id": operator_id,
                    "factory_id": f["factory_id"],
                    "operator_name": f"{random.choice(first)} {random.choice(last)}",
                    "hire_date": (
                        self.start_date - timedelta(days=random.randint(60, 4000))
                    ).isoformat(),
                    "certification_level": random.choice(["Trainee", "Standard", "Senior", "Master"]),
                    "shift_preference": random.choice(["S1", "S2", "S3"]),
                })
        df = pd.DataFrame(rows)
        logger.info("Generated {} operators.", len(df))
        return df

    def build_shifts(self) -> pd.DataFrame:
        """Build the shifts dimension table (static reference data)."""
        rows = []
        for s in self.cfg["shifts"]:
            start_t = datetime.strptime(s["start"], "%H:%M").time()
            end_t = datetime.strptime(s["end"], "%H:%M").time()
            duration_h = (
                (datetime.combine(date.today(), end_t) - datetime.combine(date.today(), start_t))
                .seconds / 3600
            )
            if duration_h <= 0:
                duration_h += 24  # overnight shift wrap-around
            rows.append({
                "shift_id": s["id"],
                "shift_name": s["name"],
                "start_time": s["start"],
                "end_time": s["end"],
                "duration_hours": duration_h,
            })
        df = pd.DataFrame(rows)
        logger.info("Generated {} shift definitions.", len(df))
        return df

    # ------------------------------------------------------------------ #
    # Fact table builders
    # ------------------------------------------------------------------ #
    def build_production_records(
        self,
        machines: pd.DataFrame,
        operators: pd.DataFrame,
        shifts: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build the central production_records fact table: one row per
        machine / calendar date / shift, holding planned time, run time,
        good/scrap counts, and the operator assigned.

        This table is the backbone from which OEE and most other KPIs are
        derived downstream.
        """
        dates = self._date_range()
        shift_ids = shifts["shift_id"].tolist()
        shift_hours = dict(zip(shifts["shift_id"], shifts["duration_hours"]))
        operators_by_factory = operators.groupby("factory_id")["operator_id"].apply(list).to_dict()

        rows = []
        for _, m in machines.iterrows():
            ideal_cycle = m["ideal_cycle_time_seconds"]
            factory_ops = operators_by_factory.get(m["factory_id"], ["OP0001"])

            # Slight per-machine performance/quality "personality" so KPI
            # trends look realistic instead of pure noise.
            base_perf = self.rng.normal(0.90, 0.05)
            base_qual = self.rng.normal(0.97, 0.015)

            for d in dates:
                # Not every machine runs every shift on every day (weekends
                # lighter, occasional idle days) — mimics real scheduling.
                is_weekend = d.weekday() >= 5
                for shift_id in shift_ids:
                    run_probability = 0.55 if is_weekend else 0.95
                    if self.rng.random() > run_probability:
                        continue  # machine not scheduled this shift

                    planned_minutes = shift_hours[shift_id] * 60
                    # Small monthly seasonality: dip mid-cycle (simulated demand curve)
                    seasonal = 1 + 0.06 * np.sin(2 * np.pi * (d.timetuple().tm_yday / 365))

                    downtime_minutes = max(0.0, self.rng.normal(25, 20))
                    downtime_minutes = min(downtime_minutes, planned_minutes * 0.6)
                    run_time_minutes = max(0.0, planned_minutes - downtime_minutes)

                    performance_rate = float(np.clip(base_perf * seasonal + self.rng.normal(0, 0.03), 0.4, 1.05))
                    theoretical_units = (run_time_minutes * 60) / ideal_cycle
                    total_units_produced = max(0, round(theoretical_units * performance_rate))

                    quality_rate = float(np.clip(base_qual + self.rng.normal(0, 0.01), 0.80, 1.0))
                    good_units = round(total_units_produced * quality_rate)
                    scrap_units = max(0, total_units_produced - good_units)

                    rows.append({
                        "date": d.isoformat(),
                        "shift_id": shift_id,
                        "factory_id": m["factory_id"],
                        "line_id": m["line_id"],
                        "machine_id": m["machine_id"],
                        "operator_id": random.choice(factory_ops),
                        "planned_production_time_minutes": round(planned_minutes, 1),
                        "downtime_minutes": round(downtime_minutes, 1),
                        "run_time_minutes": round(run_time_minutes, 1),
                        "ideal_cycle_time_seconds": ideal_cycle,
                        "total_units_produced": total_units_produced,
                        "good_units": good_units,
                        "scrap_units": scrap_units,
                    })

        df = pd.DataFrame(rows)
        df.insert(0, "record_id", [f"PR{str(i).zfill(7)}" for i in range(1, len(df) + 1)])

        # --- Inject realistic data-quality issues for the cleaning module ---
        df = self._inject_missing_values(df, cols=["downtime_minutes", "operator_id"], frac=0.01)
        df = self._inject_duplicates(df, frac=0.005)

        logger.info("Generated {} production records.", len(df))
        return df

    def build_downtime_events(
        self, production_records: pd.DataFrame, machines: pd.DataFrame
    ) -> pd.DataFrame:
        """Build downtime_events: granular stoppage events tied to production records.

        Splits each production record's aggregate downtime into 1..N
        discrete events with reason codes — mirroring how a real
        Andon/CMMS system logs stoppages.
        """
        reason_codes = self.cfg["downtime"]["reason_codes"]
        rows = []
        event_id = 1
        ideal_cycle_by_machine = dict(zip(machines["machine_id"], machines["ideal_cycle_time_seconds"]))

        # Only split records that actually have meaningful downtime.
        candidates = production_records[production_records["downtime_minutes"].fillna(0) > 5]

        for _, rec in candidates.iterrows():
            total_dt = rec["downtime_minutes"] if pd.notna(rec["downtime_minutes"]) else 0
            if total_dt <= 0:
                continue
            n_events = 1 if total_dt < 30 else random.randint(1, 3)
            splits = np.diff(
                [0] + sorted(self.rng.uniform(0, total_dt, n_events - 1)) + [total_dt]
            ) if n_events > 1 else [total_dt]

            shift_start = datetime.fromisoformat(rec["date"])
            for dur in splits:
                rows.append({
                    "event_id": f"DT{str(event_id).zfill(7)}",
                    "record_id": rec["record_id"],
                    "date": rec["date"],
                    "shift_id": rec["shift_id"],
                    "factory_id": rec["factory_id"],
                    "line_id": rec["line_id"],
                    "machine_id": rec["machine_id"],
                    "reason_code": random.choice(reason_codes),
                    "duration_minutes": round(float(dur), 1),
                    "is_planned": random.random() < 0.2,
                    "start_time": (
                        shift_start + timedelta(minutes=random.randint(0, 420))
                    ).isoformat(),
                })
                event_id += 1

        df = pd.DataFrame(rows)
        df = self._inject_missing_values(df, cols=["reason_code"], frac=0.02)
        logger.info("Generated {} downtime events.", len(df))
        return df

    def build_quality_inspections_and_defects(
        self, production_records: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Build quality_inspections and the linked defects fact table."""
        lo, hi = self.cfg["quality"]["inspections_per_shift"]
        base_rate = self.cfg["quality"]["base_defect_rate"]
        defect_types = self.cfg["quality"]["defect_types"]

        inspections, defects = [], []
        insp_id, defect_id = 1, 1

        for _, rec in production_records.iterrows():
            n_insp = random.randint(lo, hi)
            units_available = max(rec["total_units_produced"], 1)
            for _ in range(n_insp):
                sample_size = min(units_available, random.randint(5, 30))
                # Defect probability varies slightly per record (process drift)
                defect_prob = float(np.clip(base_rate + self.rng.normal(0, 0.01), 0.001, 0.25))
                n_defective = int(self.rng.binomial(sample_size, defect_prob))
                passed = n_defective == 0

                inspection_id = f"QI{str(insp_id).zfill(7)}"
                insp_id += 1
                inspections.append({
                    "inspection_id": inspection_id,
                    "record_id": rec["record_id"],
                    "date": rec["date"],
                    "shift_id": rec["shift_id"],
                    "factory_id": rec["factory_id"],
                    "line_id": rec["line_id"],
                    "machine_id": rec["machine_id"],
                    "sample_size": sample_size,
                    "defective_units": n_defective,
                    "result": "Pass" if passed else "Fail",
                    "inspector_id": rec["operator_id"],
                })

                for _ in range(n_defective):
                    defects.append({
                        "defect_id": f"DF{str(defect_id).zfill(7)}",
                        "inspection_id": inspection_id,
                        "record_id": rec["record_id"],
                        "date": rec["date"],
                        "factory_id": rec["factory_id"],
                        "line_id": rec["line_id"],
                        "machine_id": rec["machine_id"],
                        "defect_type": random.choice(defect_types),
                        "severity": random.choices(
                            ["Minor", "Major", "Critical"], weights=[0.6, 0.32, 0.08]
                        )[0],
                        "disposition": random.choices(
                            ["Scrap", "Rework", "Use-as-is"], weights=[0.5, 0.4, 0.1]
                        )[0],
                    })
                    defect_id += 1

        insp_df = pd.DataFrame(inspections)
        defect_df = pd.DataFrame(defects)
        insp_df = self._inject_missing_values(insp_df, cols=["inspector_id"], frac=0.015)

        logger.info("Generated {} quality inspections and {} defects.", len(insp_df), len(defect_df))
        return insp_df, defect_df

    def build_sensor_readings(self, machines: pd.DataFrame) -> pd.DataFrame:
        """Build high-frequency sensor_readings for each machine.

        Uses vectorized NumPy generation (rather than row-by-row Python
        loops) since this table is by far the largest in the dataset.
        """
        sensor_cfg = self.cfg["sensors"]["types"]
        interval_min = self.cfg["sensors"]["reading_interval_minutes"]

        # Build the shared timestamp index once.
        n_days = (self.end_date - self.start_date).days
        start_dt = datetime.combine(self.start_date, time(0, 0))
        n_points = int((n_days * 24 * 60) / interval_min)
        timestamps = [start_dt + timedelta(minutes=interval_min * i) for i in range(n_points)]
        ts_array = np.array(timestamps)
        n = len(ts_array)

        frames = []
        for _, m in machines.iterrows():
            machine_frame = {
                "machine_id": np.repeat(m["machine_id"], n),
                "factory_id": np.repeat(m["factory_id"], n),
                "line_id": np.repeat(m["line_id"], n),
                "timestamp": ts_array,
            }
            base_df = pd.DataFrame(machine_frame)

            for sensor_name, params in sensor_cfg.items():
                lo, hi = params["normal_range"]
                mean = (lo + hi) / 2
                std = (hi - lo) / 6  # ~99.7% within normal range
                values = self.rng.normal(mean, std, n)

                # Inject occasional anomaly spikes (equipment degradation events)
                anomaly_mask = self.rng.random(n) < 0.003
                values[anomaly_mask] += self.rng.normal(hi * 0.6, hi * 0.2, anomaly_mask.sum())
                base_df[sensor_name] = np.round(values, 2)

            frames.append(base_df)

        df = pd.concat(frames, ignore_index=True)

        # Melt to long format: one row per (machine, timestamp, sensor_type, value)
        # -> more realistic historian export shape & keeps file sizes sane per sensor.
        id_vars = ["machine_id", "factory_id", "line_id", "timestamp"]
        value_vars = list(sensor_cfg.keys())
        long_df = df.melt(id_vars=id_vars, value_vars=value_vars,
                           var_name="sensor_type", value_name="reading_value")
        long_df["unit"] = long_df["sensor_type"].map({k: v["unit"] for k, v in sensor_cfg.items()})

        long_df = self._inject_missing_values(long_df, cols=["reading_value"], frac=0.005)
        logger.info("Generated {} sensor readings.", len(long_df))
        return long_df

    # ------------------------------------------------------------------ #
    # Data-quality injection helpers (deliberate imperfections)
    # ------------------------------------------------------------------ #
    def _inject_missing_values(self, df: pd.DataFrame, cols: list[str], frac: float) -> pd.DataFrame:
        """Randomly null out a fraction of values in given columns."""
        df = df.copy()
        for col in cols:
            if col not in df.columns or len(df) == 0:
                continue
            mask = self.rng.random(len(df)) < frac
            df.loc[mask, col] = np.nan
        return df

    def _inject_duplicates(self, df: pd.DataFrame, frac: float) -> pd.DataFrame:
        """Append a small number of duplicate rows to simulate export glitches."""
        if len(df) == 0:
            return df
        n_dupes = max(1, int(len(df) * frac))
        dupes = df.sample(n=n_dupes, random_state=self.seed, replace=False)
        return pd.concat([df, dupes], ignore_index=True)

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    def generate_all(self) -> GeneratedDataset:
        """Run the full generation pipeline and return a GeneratedDataset."""
        logger.info("Starting full dataset generation...")

        factories = self.build_factories()
        lines = self.build_lines(factories)
        machines = self.build_machines(lines)
        operators = self.build_operators(factories)
        shifts = self.build_shifts()

        production_records = self.build_production_records(machines, operators, shifts)
        downtime_events = self.build_downtime_events(production_records, machines)
        quality_inspections, defects = self.build_quality_inspections_and_defects(production_records)
        sensor_readings = self.build_sensor_readings(machines)

        logger.success("Dataset generation complete.")
        return GeneratedDataset(
            factories=factories,
            production_lines=lines,
            machines=machines,
            operators=operators,
            shifts=shifts,
            production_records=production_records,
            downtime_events=downtime_events,
            quality_inspections=quality_inspections,
            defects=defects,
            sensor_readings=sensor_readings,
        )
