"""
pdf_report.py
=============
Builds a PDF KPI report combining headline metrics, a KPI table, and
embedded chart images (rendered upstream by ``visualization.charts`` as
PNG files) using ``fpdf2`` — a lightweight, dependency-free PDF library
well suited for programmatic report generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fpdf import FPDF

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)


class PDFReportBuilder(FPDF):
    """Extends FPDF with a manufacturing-report-specific header/footer and helpers."""

    def __init__(self, title: str = "Manufacturing KPI Report"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    # ------------------------------------------------------------------ #
    # Page header / footer (called automatically by FPDF on add_page)
    # ------------------------------------------------------------------ #
    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(31, 78, 120)
        self.cell(0, 10, self.report_title, ln=True, align="C")
        self.set_draw_color(31, 78, 120)
        self.line(10, 18, 200, 18)
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    # ------------------------------------------------------------------ #
    # Content helpers
    # ------------------------------------------------------------------ #
    def add_section_title(self, text: str) -> None:
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(31, 78, 120)
        self.ln(2)
        self.cell(0, 8, text, ln=True)
        self.set_text_color(0, 0, 0)

    def add_paragraph(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def add_kpi_cards(self, kpis: dict[str, str]) -> None:
        """Render a row of headline KPI cards."""
        self.set_font("Helvetica", "", 9)
        n = len(kpis)
        card_width = 190 / n
        start_x, start_y = self.get_x(), self.get_y()

        for i, (label, value) in enumerate(kpis.items()):
            x = start_x + i * card_width
            self.set_xy(x, start_y)
            self.set_fill_color(240, 244, 248)
            self.set_draw_color(200, 200, 200)
            self.rect(x, start_y, card_width - 2, 20, style="DF")
            self.set_xy(x, start_y + 3)
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(31, 78, 120)
            self.cell(card_width - 2, 7, value, align="C", ln=0)
            self.set_xy(x, start_y + 11)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(90, 90, 90)
            self.cell(card_width - 2, 6, label, align="C", ln=0)

        self.set_xy(start_x, start_y + 24)
        self.set_text_color(0, 0, 0)

    def add_table(self, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None) -> None:
        """Render a simple bordered table."""
        available_width = 190
        n_cols = len(headers)
        widths = col_widths or [available_width / n_cols] * n_cols

        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(31, 78, 120)
        self.set_text_color(255, 255, 255)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, align="C", fill=True)
        self.ln()

        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(0, 0, 0)
        fill = False
        for row in rows:
            self.set_fill_color(245, 247, 250) if fill else self.set_fill_color(255, 255, 255)
            for val, w in zip(row, widths):
                self.cell(w, 6.5, str(val), border=1, align="C", fill=True)
            self.ln()
            fill = not fill

    def add_image(self, image_path: str | Path, width: float = 190) -> None:
        """Embed a chart PNG, adding a page break first if it won't fit."""
        if self.get_y() > 230:
            self.add_page()
        self.image(str(image_path), x=(210 - width) / 2, w=width)
        self.ln(4)

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #
    def save(self, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.output(str(out_path))
        logger.success("PDF report saved -> {}", out_path)
        return out_path
