#!/usr/bin/env python3
"""
main.py
=======
End-to-end pipeline entry point for the Manufacturing Analytics Platform.

Run with:
    python main.py                  # full pipeline, default config
    python main.py --skip-generate  # reuse existing data/raw files
    python main.py --dry-run        # validate config without processing
    python main.py --debug          # verbose logging
    python main.py --help           # see all options

Pipeline stages
----------------
1. GENERATE  — synthesize >= 12 months of manufacturing data (CSV + Excel)
2. CLEAN     — validate schema, fix dtypes, handle missing/dupes/outliers
3. KPI       — compute OEE, MTBF, MTTR, scrap/defect rate, throughput, etc.
4. VISUALIZE — build interactive Plotly dashboard (HTML)
5. REPORT    — build Excel KPI workbook + PDF executive report
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from manufacturing_analytics.dashboards.plotly_dashboard import DashboardBuilder
from manufacturing_analytics.data_generation.exporter import export_dataset
from manufacturing_analytics.data_generation.generator import ManufacturingDataGenerator
from manufacturing_analytics.data_processing.cleaning import DataCleaner
from manufacturing_analytics.kpi.calculations import KPICalculator
from manufacturing_analytics.reporting.excel_report import ExcelReportBuilder
from manufacturing_analytics.reporting.pdf_report import PDFReportBuilder
from manufacturing_analytics.utils.config import load_config, resolve_path, validate_config
from manufacturing_analytics.utils.logger import configure_logging, get_logger
from manufacturing_analytics.utils.validators import PipelineValidator
from manufacturing_analytics.visualization.charts import ChartFactory

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manufacturing Analytics Platform pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Full pipeline with default config
  python main.py --skip-generate    # Use existing data
  python main.py --dry-run          # Validate config only
  python main.py --config custom.yaml --debug  # Custom config with verbose logs
        """
    )
    parser.add_argument(
        "--skip-generate", action="store_true",
        help="Reuse existing CSVs in data/raw instead of regenerating."
    )
    parser.add_argument(
        "--config", default=None, 
        help="Path to config.yaml (default: config/config.yaml)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate configuration and data paths without processing."
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable verbose debug logging."
    )
    parser.add_argument(
        "--skip-report", action="store_true",
        help="Skip Excel and PDF report generation."
    )
    return parser.parse_args()


def load_or_generate_data(config: dict, raw_dir: Path, skip_generate: bool) -> dict[str, pd.DataFrame]:
    """Stage 1: generate synthetic data (or load existing CSVs)."""
    if skip_generate and raw_dir.exists() and any(raw_dir.glob("*.csv")):
        logger.info("Skipping generation — loading existing CSVs from {}", raw_dir)
        return {p.stem: pd.read_csv(p) for p in raw_dir.glob("*.csv")}

    logger.info("=== STAGE 1/5: GENERATING SYNTHETIC DATA ===")
    generator = ManufacturingDataGenerator(config)
    dataset = generator.generate_all()
    export_dataset(dataset, raw_dir)
    return dataset.as_dict()


def clean_all_tables(config: dict, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Stage 2: clean/validate each table with table-specific column rules."""
    logger.info("=== STAGE 2/5: CLEANING & VALIDATING DATA ===")
    cleaner = DataCleaner(config)
    cleaned = {}

    cleaned["production_records"], _ = cleaner.clean(
        tables["production_records"], "production",
        date_cols=["date"],
        numeric_cols=["planned_production_time_minutes", "downtime_minutes", "run_time_minutes",
                      "total_units_produced", "good_units", "scrap_units"],
        category_cols=["shift_id", "factory_id", "line_id", "machine_id"],
        outlier_cols=["downtime_minutes", "total_units_produced"],
        non_negative_cols=["total_units_produced", "good_units", "scrap_units", "downtime_minutes"],
    )
    cleaned["downtime_events"], _ = cleaner.clean(
        tables["downtime_events"], "downtime",
        date_cols=["date", "start_time"],
        numeric_cols=["duration_minutes"],
        category_cols=["reason_code", "shift_id"],
        outlier_cols=["duration_minutes"],
        non_negative_cols=["duration_minutes"],
    )
    cleaned["quality_inspections"], _ = cleaner.clean(
        tables["quality_inspections"], "quality",
        date_cols=["date"],
        numeric_cols=["sample_size", "defective_units"],
        category_cols=["result", "shift_id"],
        non_negative_cols=["sample_size", "defective_units"],
    )
    cleaned["defects"], _ = cleaner.clean(
        tables["defects"], "defects",
        date_cols=["date"],
        category_cols=["defect_type", "severity", "disposition"],
    )
    cleaned["sensor_readings"], _ = cleaner.clean(
        tables["sensor_readings"], "sensor",
        date_cols=["timestamp"],
        numeric_cols=["reading_value"],
        category_cols=["sensor_type"],
        outlier_cols=["reading_value"],
    )

    # Pass-through dimension tables (already clean, generated in-code)
    for dim in ["factories", "production_lines", "machines", "operators", "shifts"]:
        cleaned[dim] = tables[dim]

    return cleaned


def compute_kpis(config: dict, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Stage 3: compute row-level and aggregated KPIs."""
    logger.info("=== STAGE 3/5: CALCULATING KPIs ===")
    kpi_calc = KPICalculator(config)

    production = kpi_calc.add_oee_components(tables["production_records"])
    production["date"] = pd.to_datetime(production["date"])
    production["month"] = production["date"].dt.to_period("M").astype(str)

    monthly_kpis = kpi_calc.aggregate_kpis(production, group_by=["month"])
    factory_kpis = kpi_calc.aggregate_kpis(production, group_by=["factory_id"])
    machine_kpis = kpi_calc.aggregate_kpis(production, group_by=["machine_id"])
    shift_kpis = kpi_calc.aggregate_kpis(production, group_by=["shift_id"])

    mtbf_mttr_machine = kpi_calc.calculate_mtbf_mttr(
        tables["downtime_events"], production, group_by=["machine_id"]
    )
    defect_rate_factory = kpi_calc.calculate_defect_rate(
        tables["quality_inspections"], group_by=["factory_id"]
    )
    pareto = kpi_calc.pareto_analysis(tables["defects"], category_col="defect_type")

    return {
        "production_with_kpis": production,
        "monthly_kpis": monthly_kpis,
        "factory_kpis": factory_kpis,
        "machine_kpis": machine_kpis,
        "shift_kpis": shift_kpis,
        "mtbf_mttr_machine": mtbf_mttr_machine,
        "defect_rate_factory": defect_rate_factory,
        "pareto": pareto,
    }


def build_dashboard(kpis: dict[str, pd.DataFrame], out_path: Path) -> None:
    """Stage 4: assemble the interactive Plotly HTML dashboard."""
    logger.info("=== STAGE 4/5: BUILDING DASHBOARD ===")
    cf = ChartFactory()
    dash = DashboardBuilder(
        title="Manufacturing Operations Dashboard",
        subtitle=f"Generated {pd.Timestamp.now():%Y-%m-%d %H:%M} UTC",
    )

    overall_oee = kpis["production_with_kpis"]["oee"].mean()
    dash.add_figure(cf.kpi_gauge(overall_oee, "Overall OEE", target=0.75))
    dash.add_figure(cf.bar_chart(kpis["factory_kpis"], x="factory_id", y="oee",
                                   title="OEE by Factory"))
    dash.add_figure(cf.line_chart(kpis["monthly_kpis"], x="month", y="oee",
                                    title="Monthly OEE Trend"), full_width=True)
    dash.add_figure(cf.bar_chart(kpis["shift_kpis"], x="shift_id", y="oee", title="OEE by Shift"))
    dash.add_figure(cf.box_chart(kpis["production_with_kpis"], x="factory_id", y="oee",
                                   title="OEE Distribution by Factory"))
    dash.add_figure(cf.pareto_chart(kpis["pareto"], category_col="defect_type",
                                      title="Defect Pareto Analysis"), full_width=True)
    dash.add_figure(cf.histogram(kpis["production_with_kpis"], x="cycle_time_actual_seconds",
                                   title="Cycle Time Distribution"))
    dash.add_figure(cf.scatter_chart(kpis["factory_kpis"], x="availability", y="quality",
                                       size="total_units_produced", color="factory_id",
                                       title="Availability vs. Quality by Factory"))
    monthly_ctrl = kpis["monthly_kpis"].sort_values("month")
    dash.add_figure(cf.control_chart(monthly_ctrl, x="month", y="oee",
                                       title="OEE Control Chart (Monthly)"), full_width=True)

    dash.save(out_path)


def build_reports(config: dict, kpis: dict[str, pd.DataFrame], excel_dir: Path, pdf_dir: Path, chart_tmp_dir: Path) -> None:
    """Stage 5: build the Excel KPI workbook and the PDF executive report."""
    logger.info("=== STAGE 5/5: BUILDING REPORTS ===")
    cf = ChartFactory()
    production = kpis["production_with_kpis"]

    summary = {
        "OEE": production["oee"].mean(),
        "Availability": production["availability"].mean(),
        "Performance": production["performance"].mean(),
        "Quality": production["quality"].mean(),
        "Scrap Rate": production["scrap_rate"].mean(),
    }

    # --- Excel workbook ---
    excel = ExcelReportBuilder(kpi_targets=config.get("kpi_targets", {}))
    excel.add_title_sheet(
        "Manufacturing KPI Report", "Automated KPI summary and breakdowns",
        f"{production['date'].min():%Y-%m-%d} to {production['date'].max():%Y-%m-%d}",
    )
    excel.add_kpi_summary_sheet(summary)
    excel.add_dataframe_sheet(kpis["monthly_kpis"], "Monthly KPIs",
                                percent_cols=["availability", "performance", "quality", "oee", "scrap_rate"])
    excel.add_dataframe_sheet(kpis["factory_kpis"], "Factory KPIs",
                                percent_cols=["availability", "performance", "quality", "oee", "scrap_rate"])
    excel.add_dataframe_sheet(kpis["machine_kpis"], "Machine KPIs",
                                percent_cols=["availability", "performance", "quality", "oee", "scrap_rate"])
    excel.add_dataframe_sheet(kpis["mtbf_mttr_machine"], "MTBF & MTTR")
    excel.add_dataframe_sheet(kpis["defect_rate_factory"], "Defect Rate by Factory",
                                percent_cols=["defect_rate", "first_pass_yield"])
    excel.add_dataframe_sheet(kpis["pareto"], "Defect Pareto")
    excel.save(excel_dir / "manufacturing_kpi_report.xlsx")

    # --- PDF report (with embedded static charts) ---
    chart_tmp_dir.mkdir(parents=True, exist_ok=True)
    trend_png = cf.save_static_line_chart(
        kpis["monthly_kpis"].sort_values("month"), x="month", y="oee",
        out_path=chart_tmp_dir / "monthly_oee.png", title="Monthly OEE Trend",
    )
    factory_png = cf.save_static_bar_chart(
        kpis["factory_kpis"], x="factory_id", y="oee",
        out_path=chart_tmp_dir / "factory_oee.png", title="OEE by Factory",
    )
    pareto_png = cf.save_static_pareto_chart(
        kpis["pareto"], category_col="defect_type",
        out_path=chart_tmp_dir / "defect_pareto.png", title="Defect Pareto Analysis",
    )
    box_png = cf.save_static_box_chart(
        production, x="factory_id", y="oee",
        out_path=chart_tmp_dir / "oee_box.png", title="OEE Distribution by Factory",
    )

    pdf = PDFReportBuilder(title="Manufacturing KPI Executive Report")
    pdf.add_page()
    pdf.add_section_title("Executive Summary")
    pdf.add_paragraph(
        "This automated report summarizes manufacturing performance across all factories, "
        "lines, and machines for the analyzed period, based on standard OEE "
        "(Overall Equipment Effectiveness) methodology."
    )
    pdf.add_kpi_cards({
        "OEE": f"{summary['OEE']*100:.1f}%",
        "Availability": f"{summary['Availability']*100:.1f}%",
        "Performance": f"{summary['Performance']*100:.1f}%",
        "Quality": f"{summary['Quality']*100:.1f}%",
        "Scrap Rate": f"{summary['Scrap Rate']*100:.1f}%",
    })
    pdf.ln(6)
    pdf.add_section_title("Monthly OEE Trend")
    pdf.add_image(trend_png)
    pdf.add_section_title("OEE by Factory")
    pdf.add_image(factory_png)

    pdf.add_page()
    pdf.add_section_title("OEE Distribution by Factory")
    pdf.add_image(box_png)
    pdf.add_section_title("Defect Pareto Analysis")
    pdf.add_image(pareto_png)

    pdf.add_page()
    pdf.add_section_title("Factory-Level KPI Table")
    factory_tbl = kpis["factory_kpis"][["factory_id", "oee", "availability", "performance", "quality", "scrap_rate"]].copy()
    for c in ["oee", "availability", "performance", "quality", "scrap_rate"]:
        factory_tbl[c] = (factory_tbl[c] * 100).round(1).astype(str) + "%"
    pdf.add_table(
        headers=["Factory", "OEE", "Availability", "Performance", "Quality", "Scrap Rate"],
        rows=factory_tbl.values.tolist(),
    )

    pdf.save(pdf_dir / "manufacturing_kpi_report.pdf")


def main() -> None:
    """Execute the full manufacturing analytics pipeline."""
    args = parse_args()

    # Configure logging
    log_level = "DEBUG" if args.debug else "INFO"
    configure_logging(log_level)

    logger.info("🏭 Manufacturing Analytics Platform")
    logger.info("=" * 60)

    try:
        # Load and validate configuration
        config_path = args.config if args.config else None
        logger.info("Loading configuration...")
        config = load_config(config_path)

        # Validate configuration
        validation_errors = validate_config(config)
        if validation_errors:
            logger.error("Configuration validation failed:")
            for err in validation_errors:
                logger.error("  ✗ {}", err)
            sys.exit(1)

        logger.info("✓ Configuration validated successfully")

        # Resolve paths
        raw_dir = resolve_path(config["paths"]["raw_data_dir"])
        processed_dir = resolve_path(config["paths"]["processed_data_dir"])
        dashboards_dir = resolve_path(config["paths"]["dashboards_dir"])
        reports_dir = resolve_path(config["paths"]["reports_dir"])
        chart_tmp_dir = reports_dir / "_chart_tmp"

        # Dry-run mode: validate and exit
        if args.dry_run:
            logger.info("Running in DRY-RUN mode — validating configuration only")
            validator = PipelineValidator()
            path_errors = validator.validate_paths(config)
            if path_errors:
                for err in path_errors:
                    logger.error("  ✗ {}", err)
                sys.exit(1)
            logger.info("✓ Dry-run validation passed — ready to process data")
            sys.exit(0)

        # Pipeline execution
        t0 = time.time()

        # Stage 1: Generate/Load raw data
        try:
            raw_tables = load_or_generate_data(config, raw_dir, args.skip_generate)
            logger.info("✓ Stage 1 complete: {} tables loaded", len(raw_tables))
        except Exception as e:
            logger.error("✗ Stage 1 failed: {}", str(e))
            raise

        # Stage 2: Clean data
        try:
            clean_tables = clean_all_tables(config, raw_tables)
            logger.info("✓ Stage 2 complete: {} tables cleaned", len(clean_tables))

            processed_dir.mkdir(parents=True, exist_ok=True)
            for name, df in clean_tables.items():
                output_path = processed_dir / f"{name}_clean.csv"
                df.to_csv(output_path, index=False)
                logger.debug("Saved {}", output_path)

        except Exception as e:
            logger.error("✗ Stage 2 failed: {}", str(e))
            raise

        # Stage 3: Compute KPIs
        try:
            kpis = compute_kpis(config, clean_tables)
            logger.info("✓ Stage 3 complete: {} KPI tables calculated", len(kpis))

            processed_dir.mkdir(parents=True, exist_ok=True)
            for name, df in kpis.items():
                output_path = processed_dir / f"{name}.csv"
                df.to_csv(output_path, index=False)
                logger.debug("Saved {}", output_path)

        except Exception as e:
            logger.error("✗ Stage 3 failed: {}", str(e))
            raise

        # Stage 4: Build dashboard
        try:
            dashboards_dir.mkdir(parents=True, exist_ok=True)
            build_dashboard(kpis, dashboards_dir / "manufacturing_dashboard.html")
            logger.info("✓ Stage 4 complete: Dashboard built")
        except Exception as e:
            logger.error("✗ Stage 4 failed: {}", str(e))
            if not args.skip_report:
                raise

        # Stage 5: Build reports (optional)
        if not args.skip_report:
            try:
                reports_dir.mkdir(parents=True, exist_ok=True)
                (reports_dir / "excel").mkdir(parents=True, exist_ok=True)
                (reports_dir / "pdf").mkdir(parents=True, exist_ok=True)
                build_reports(config, kpis, reports_dir / "excel", reports_dir / "pdf", chart_tmp_dir)
                logger.info("✓ Stage 5 complete: Reports built")
            except Exception as e:
                logger.error("✗ Stage 5 failed: {}", str(e))
                raise
        else:
            logger.info("⊘ Stage 5 skipped: Report generation disabled")

        # Success summary
        elapsed = time.time() - t0
        logger.success("=" * 60)
        logger.success("✓ Pipeline completed successfully in {:.1f}s", elapsed)
        logger.info("")
        logger.info("📊 Output files:")
        logger.info("  Dashboard: {}", (dashboards_dir / "manufacturing_dashboard.html").relative_to(Path.cwd()))
        if not args.skip_report:
            logger.info("  Excel report: {}", (reports_dir / "excel" / "manufacturing_kpi_report.xlsx").relative_to(Path.cwd()))
            logger.info("  PDF report: {}", (reports_dir / "pdf" / "manufacturing_kpi_report.pdf").relative_to(Path.cwd()))
        logger.info("  Processed data: {}", processed_dir.relative_to(Path.cwd()))

    except Exception as e:
        logger.error("=" * 60)
        logger.error("✗ Pipeline failed with error:")
        logger.error("  {}", str(e))
        if args.debug:
            logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()

