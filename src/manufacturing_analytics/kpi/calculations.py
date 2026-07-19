"""
calculations.py
================
Manufacturing KPI engineering.

All formulas follow standard, widely-used industrial engineering
definitions (SEMI E10 / lean manufacturing conventions):

    Availability = Run Time / Planned Production Time
    Performance  = (Ideal Cycle Time * Total Units) / Run Time
    Quality      = Good Units / Total Units
    OEE          = Availability * Performance * Quality

    MTBF (Mean Time Between Failures) = Total Uptime / Number of Failures
    MTTR (Mean Time To Repair)        = Total Downtime / Number of Repairs

    Scrap Rate   = Scrap Units / Total Units Produced
    Defect Rate  = Defective Units / Units Inspected
    Cycle Time   = Run Time / Total Units Produced   (actual, vs. ideal)
    Utilization  = Run Time / Total Calendar Time available
    Throughput   = Total Units Produced / Run Time (units per hour)

Every function accepts and returns plain pandas DataFrames/Series so it
can be unit tested in isolation and reused from notebooks, dashboards,
the reporting engine, or a future REST API layer without modification.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)


class KPICalculator:
    """Computes standard manufacturing KPIs from cleaned fact tables."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.targets = (config or {}).get("kpi_targets", {})

    # ------------------------------------------------------------------ #
    # Row-level OEE components (added directly onto production_records)
    # ------------------------------------------------------------------ #
    def add_oee_components(self, production: pd.DataFrame) -> pd.DataFrame:
        """Add availability, performance, quality, and OEE columns.

        Expects columns: planned_production_time_minutes, run_time_minutes,
        ideal_cycle_time_seconds, total_units_produced, good_units.
        """
        df = production.copy()

        df["availability"] = self._safe_divide(
            df["run_time_minutes"], df["planned_production_time_minutes"]
        )
        ideal_time_minutes = (df["ideal_cycle_time_seconds"] * df["total_units_produced"]) / 60
        df["performance"] = self._safe_divide(ideal_time_minutes, df["run_time_minutes"])
        df["performance"] = df["performance"].clip(upper=1.5)  # cap unrealistic spikes

        df["quality"] = self._safe_divide(df["good_units"], df["total_units_produced"])

        df["oee"] = df["availability"] * df["performance"] * df["quality"]

        # Supplementary rate metrics
        df["scrap_rate"] = self._safe_divide(df["scrap_units"], df["total_units_produced"])
        df["cycle_time_actual_seconds"] = self._safe_divide(
            df["run_time_minutes"] * 60, df["total_units_produced"]
        )
        df["utilization"] = self._safe_divide(
            df["run_time_minutes"], df["planned_production_time_minutes"]
        )
        df["throughput_units_per_hour"] = self._safe_divide(
            df["total_units_produced"], df["run_time_minutes"] / 60
        )

        logger.info("Added OEE + rate KPI columns to {} production records.", len(df))
        return df

    # ------------------------------------------------------------------ #
    # Reliability metrics: MTBF / MTTR
    # ------------------------------------------------------------------ #
    def calculate_mtbf_mttr(
        self, downtime_events: pd.DataFrame, production: pd.DataFrame, group_by: list[str]
    ) -> pd.DataFrame:
        """Calculate MTBF and MTTR grouped by arbitrary dimensions (e.g. machine_id).

        MTBF = total uptime / number of failure (unplanned downtime) events
        MTTR = total unplanned downtime / number of failure events

        Only *unplanned* downtime events count as "failures" for MTBF/MTTR;
        planned maintenance / changeovers are excluded, matching standard
        reliability-engineering practice.
        """
        failures = downtime_events[downtime_events["is_planned"] == False].copy()  # noqa: E712

        failure_stats = (
            failures.groupby(group_by)
            .agg(
                failure_count=("event_id", "count"),
                total_downtime_minutes=("duration_minutes", "sum"),
            )
            .reset_index()
        )

        uptime_stats = (
            production.groupby(group_by)
            .agg(total_run_time_minutes=("run_time_minutes", "sum"))
            .reset_index()
        )

        merged = uptime_stats.merge(failure_stats, on=group_by, how="left")
        merged["failure_count"] = merged["failure_count"].fillna(0)
        merged["total_downtime_minutes"] = merged["total_downtime_minutes"].fillna(0)

        merged["mtbf_hours"] = self._safe_divide(
            merged["total_run_time_minutes"] / 60, merged["failure_count"]
        )
        merged["mttr_hours"] = self._safe_divide(
            merged["total_downtime_minutes"] / 60, merged["failure_count"]
        )

        logger.info("Calculated MTBF/MTTR grouped by {}.", group_by)
        return merged

    # ------------------------------------------------------------------ #
    # Quality metrics
    # ------------------------------------------------------------------ #
    def calculate_defect_rate(
        self, inspections: pd.DataFrame, group_by: list[str]
    ) -> pd.DataFrame:
        """Defect rate = total defective units / total units inspected, grouped."""
        result = (
            inspections.groupby(group_by)
            .agg(
                units_inspected=("sample_size", "sum"),
                defective_units=("defective_units", "sum"),
                inspections_count=("inspection_id", "count"),
                pass_count=("result", lambda s: (s == "Pass").sum()),
            )
            .reset_index()
        )
        result["defect_rate"] = self._safe_divide(result["defective_units"], result["units_inspected"])
        result["first_pass_yield"] = self._safe_divide(result["pass_count"], result["inspections_count"])
        return result

    def pareto_analysis(self, defects: pd.DataFrame, category_col: str = "defect_type") -> pd.DataFrame:
        """Classic Pareto (80/20) table: defect counts, % of total, cumulative %."""
        counts = defects[category_col].value_counts().reset_index()
        counts.columns = [category_col, "count"]
        counts = counts.sort_values("count", ascending=False).reset_index(drop=True)
        counts["pct_of_total"] = counts["count"] / counts["count"].sum() * 100
        counts["cumulative_pct"] = counts["pct_of_total"].cumsum()
        return counts

    # ------------------------------------------------------------------ #
    # Aggregation helpers
    # ------------------------------------------------------------------ #
    def aggregate_kpis(
        self, production_with_oee: pd.DataFrame, group_by: list[str]
    ) -> pd.DataFrame:
        """Aggregate row-level OEE data to a chosen grain (e.g. factory+month).

        Uses weighted averages for rate metrics (weighted by run time / units)
        rather than a naive mean-of-means, which is a common KPI mistake.
        """
        df = production_with_oee.copy()

        def _weighted_avg(values: pd.Series, weights: pd.Series) -> float:
            weights_sum = weights.sum()
            if weights_sum == 0:
                return float(np.nan)
            return float((values * weights).sum() / weights_sum)

        records = []
        for keys, grp in df.groupby(group_by):
            keys = keys if isinstance(keys, tuple) else (keys,)
            record = dict(zip(group_by, keys))
            record.update({
                "total_units_produced": grp["total_units_produced"].sum(),
                "good_units": grp["good_units"].sum(),
                "scrap_units": grp["scrap_units"].sum(),
                "planned_production_time_minutes": grp["planned_production_time_minutes"].sum(),
                "run_time_minutes": grp["run_time_minutes"].sum(),
                "downtime_minutes": grp["downtime_minutes"].sum(),
                "availability": _weighted_avg(grp["availability"], grp["planned_production_time_minutes"]),
                "performance": _weighted_avg(grp["performance"], grp["run_time_minutes"]),
                "quality": _weighted_avg(grp["quality"], grp["total_units_produced"]),
                "oee": _weighted_avg(grp["oee"], grp["planned_production_time_minutes"]),
                "scrap_rate": self._safe_divide(grp["scrap_units"].sum(), grp["total_units_produced"].sum()),
                "throughput_units_per_hour": _weighted_avg(
                    grp["throughput_units_per_hour"], grp["run_time_minutes"]
                ),
            })
            records.append(record)

        result = pd.DataFrame(records)
        logger.info("Aggregated KPIs by {} -> {} groups.", group_by, len(result))
        return result

    # ------------------------------------------------------------------ #
    # RAG (Red/Amber/Green) status classification against targets
    # ------------------------------------------------------------------ #
    def classify_status(self, value: float, kpi_name: str) -> str:
        """Classify a KPI value as Green / Amber / Red vs. configured targets."""
        target_map = {
            "oee": self.targets.get("oee_target", 0.75),
            "availability": self.targets.get("availability_target", 0.90),
            "performance": self.targets.get("performance_target", 0.90),
            "quality": self.targets.get("quality_target", 0.98),
        }
        higher_is_better_target = target_map.get(kpi_name)
        if higher_is_better_target is None:
            return "N/A"
        if pd.isna(value):
            return "N/A"
        if value >= higher_is_better_target:
            return "Green"
        if value >= higher_is_better_target * 0.9:
            return "Amber"
        return "Red"

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_divide(numerator, denominator):
        """Element-wise or scalar division that returns 0 instead of raising
        on division by zero — a frequent hazard with real production data
        (e.g. a shift with zero planned time)."""
        if np.isscalar(numerator) and np.isscalar(denominator):
            return 0.0 if not denominator else numerator / denominator
        num = pd.Series(numerator) if not isinstance(numerator, pd.Series) else numerator
        den = pd.Series(denominator) if not isinstance(denominator, pd.Series) else denominator
        with np.errstate(divide="ignore", invalid="ignore"):
            result = num / den
        return result.replace([np.inf, -np.inf], 0).fillna(0)
