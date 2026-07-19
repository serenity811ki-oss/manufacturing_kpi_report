"""
Manufacturing Analytics Platform
=================================
A production-ready toolkit for manufacturing data generation, cleaning,
KPI engineering (OEE, MTBF, MTTR, scrap/defect rates, etc.), visualization,
and automated Excel/PDF reporting.

Public API re-exports the most commonly used classes so callers can do:

    from manufacturing_analytics import (
        ManufacturingDataGenerator, DataCleaner, KPICalculator,
        ChartFactory, DashboardBuilder, ExcelReportBuilder, PDFReportBuilder,
    )
"""

from manufacturing_analytics.dashboards.plotly_dashboard import DashboardBuilder
from manufacturing_analytics.data_generation.generator import ManufacturingDataGenerator
from manufacturing_analytics.data_processing.cleaning import DataCleaner
from manufacturing_analytics.kpi.calculations import KPICalculator
from manufacturing_analytics.reporting.excel_report import ExcelReportBuilder
from manufacturing_analytics.reporting.pdf_report import PDFReportBuilder
from manufacturing_analytics.visualization.charts import ChartFactory

__version__ = "1.0.0"

__all__ = [
    "ManufacturingDataGenerator",
    "DataCleaner",
    "KPICalculator",
    "ChartFactory",
    "DashboardBuilder",
    "ExcelReportBuilder",
    "PDFReportBuilder",
]
