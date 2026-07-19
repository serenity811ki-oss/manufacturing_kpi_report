"""
charts.py
=========
Reusable chart-building functions for manufacturing analytics.

Two families of charts are provided:

1. **Plotly** (interactive, HTML) — used for the dashboards. Preferred for
   anything the user will explore interactively (hover tooltips, zoom).
2. **Matplotlib / Seaborn** (static, PNG) — used where a static image is
   required, e.g. embedding into PDF reports.

Chart types covered: line, bar, histogram, scatter, box, heatmap,
Pareto (dual-axis bar + cumulative line), and SPC control charts
(X-bar chart with UCL/LCL based on +/-3 sigma).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # headless backend — required for server/CI environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns
from plotly.subplots import make_subplots

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)

# Consistent color palette across the whole platform.
PALETTE = {
    "primary": "#1f77b4",
    "success": "#2ca02c",
    "warning": "#ff7f0e",
    "danger": "#d62728",
    "neutral": "#7f7f7f",
}
RAG_COLORS = {"Green": "#2ca02c", "Amber": "#ff7f0e", "Red": "#d62728", "N/A": "#7f7f7f"}

sns.set_theme(style="whitegrid", palette="deep")


class ChartFactory:
    """Factory of static + interactive chart builders used across the platform."""

    # ================================================================== #
    # PLOTLY (interactive) charts — used in dashboards
    # ================================================================== #
    @staticmethod
    def line_chart(
        df: pd.DataFrame, x: str, y: str, color: str | None = None,
        title: str = "", y_label: str | None = None,
    ) -> go.Figure:
        """Trend line chart, e.g. daily/monthly OEE over time."""
        fig = px.line(df, x=x, y=y, color=color, title=title, markers=True)
        fig.update_layout(template="plotly_white", yaxis_title=y_label or y)
        return fig

    @staticmethod
    def bar_chart(
        df: pd.DataFrame, x: str, y: str, color: str | None = None,
        title: str = "", orientation: str = "v",
    ) -> go.Figure:
        """Bar chart, e.g. OEE by factory or defect counts by type."""
        fig = px.bar(df, x=x, y=y, color=color, title=title, orientation=orientation,
                      text_auto=".2s")
        fig.update_layout(template="plotly_white")
        return fig

    @staticmethod
    def histogram(
        df: pd.DataFrame, x: str, nbins: int = 30, title: str = "", color: str | None = None,
    ) -> go.Figure:
        """Distribution histogram, e.g. cycle time or sensor reading distribution."""
        fig = px.histogram(df, x=x, nbins=nbins, color=color, title=title)
        fig.update_layout(template="plotly_white")
        return fig

    @staticmethod
    def scatter_chart(
        df: pd.DataFrame, x: str, y: str, color: str | None = None, size: str | None = None,
        title: str = "", trendline: str | None = None,
    ) -> go.Figure:
        """Scatter plot, e.g. cycle time vs. defect rate correlation."""
        fig = px.scatter(df, x=x, y=y, color=color, size=size, title=title,
                          trendline=trendline, opacity=0.7)
        fig.update_layout(template="plotly_white")
        return fig

    @staticmethod
    def box_chart(
        df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str = "",
    ) -> go.Figure:
        """Box plot, e.g. OEE spread by factory or shift."""
        fig = px.box(df, x=x, y=y, color=color, title=title, points="outliers")
        fig.update_layout(template="plotly_white")
        return fig

    @staticmethod
    def heatmap(
        pivot_df: pd.DataFrame, title: str = "", color_scale: str = "RdYlGn",
        z_label: str = "Value",
    ) -> go.Figure:
        """Heatmap from a pre-pivoted DataFrame (index=rows, columns=cols)."""
        fig = go.Figure(
            data=go.Heatmap(
                z=pivot_df.values,
                x=pivot_df.columns.astype(str),
                y=pivot_df.index.astype(str),
                colorscale=color_scale,
                colorbar=dict(title=z_label),
                text=np.round(pivot_df.values, 2),
                texttemplate="%{text}",
            )
        )
        fig.update_layout(title=title, template="plotly_white")
        return fig

    @staticmethod
    def pareto_chart(pareto_df: pd.DataFrame, category_col: str, title: str = "Pareto Analysis") -> go.Figure:
        """Dual-axis Pareto chart: bar = count, line = cumulative %."""
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=pareto_df[category_col], y=pareto_df["count"], name="Count",
                   marker_color=PALETTE["primary"]),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=pareto_df[category_col], y=pareto_df["cumulative_pct"],
                       name="Cumulative %", mode="lines+markers", marker_color=PALETTE["danger"]),
            secondary_y=True,
        )
        fig.add_hline(y=80, line_dash="dash", line_color="gray", secondary_y=True,
                       annotation_text="80% threshold")
        fig.update_layout(title=title, template="plotly_white")
        fig.update_yaxes(title_text="Count", secondary_y=False)
        fig.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
        return fig

    @staticmethod
    def control_chart(
        df: pd.DataFrame, x: str, y: str, title: str = "Control Chart (X-bar, +/-3 sigma)",
    ) -> go.Figure:
        """SPC (Statistical Process Control) chart with UCL/LCL/center line."""
        mean = df[y].mean()
        std = df[y].std()
        ucl, lcl = mean + 3 * std, mean - 3 * std

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="lines+markers", name=y,
                                   marker_color=PALETTE["primary"]))
        fig.add_hline(y=mean, line_color="green", annotation_text="Mean")
        fig.add_hline(y=ucl, line_color="red", line_dash="dash", annotation_text="UCL (+3σ)")
        fig.add_hline(y=lcl, line_color="red", line_dash="dash", annotation_text="LCL (-3σ)")

        out_of_control = df[(df[y] > ucl) | (df[y] < lcl)]
        if not out_of_control.empty:
            fig.add_trace(go.Scatter(
                x=out_of_control[x], y=out_of_control[y], mode="markers",
                marker=dict(color=PALETTE["danger"], size=10, symbol="x"),
                name="Out of control",
            ))
        fig.update_layout(title=title, template="plotly_white")
        return fig

    @staticmethod
    def kpi_gauge(value: float, title: str, target: float = 0.85, max_value: float = 1.0) -> go.Figure:
        """Gauge indicator for a single KPI (e.g. OEE) vs. its target."""
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=round(value * 100, 1),
            number={"suffix": "%"},
            delta={"reference": target * 100},
            title={"text": title},
            gauge={
                "axis": {"range": [0, max_value * 100]},
                "bar": {"color": PALETTE["primary"]},
                "steps": [
                    {"range": [0, target * 100 * 0.8], "color": "#fde0dc"},
                    {"range": [target * 100 * 0.8, target * 100], "color": "#fff3cd"},
                    {"range": [target * 100, max_value * 100], "color": "#d4edda"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.8,
                    "value": target * 100,
                },
            },
        ))
        return fig

    # ================================================================== #
    # MATPLOTLIB / SEABORN (static) charts — used in PDF reports
    # ================================================================== #
    @staticmethod
    def save_static_line_chart(
        df: pd.DataFrame, x: str, y: str, out_path: str | Path, title: str = "", hue: str | None = None,
    ) -> Path:
        """Save a static PNG line chart via Seaborn/Matplotlib."""
        fig, ax = plt.subplots(figsize=(9, 4.5))
        sns.lineplot(data=df, x=x, y=y, hue=hue, marker="o", ax=ax)
        ax.set_title(title)
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        out_path = Path(out_path)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    @staticmethod
    def save_static_bar_chart(
        df: pd.DataFrame, x: str, y: str, out_path: str | Path, title: str = "", hue: str | None = None,
    ) -> Path:
        """Save a static PNG bar chart via Seaborn/Matplotlib."""
        fig, ax = plt.subplots(figsize=(9, 4.5))
        if hue is None:
            sns.barplot(data=df, x=x, y=y, hue=x, ax=ax, palette="deep", legend=False)
        else:
            sns.barplot(data=df, x=x, y=y, hue=hue, ax=ax, palette="deep")
        ax.set_title(title)
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        out_path = Path(out_path)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    @staticmethod
    def save_static_pareto_chart(
        pareto_df: pd.DataFrame, category_col: str, out_path: str | Path, title: str = "Pareto Chart",
    ) -> Path:
        """Save a static PNG Pareto chart (bar + cumulative line, dual axis)."""
        fig, ax1 = plt.subplots(figsize=(9, 4.5))
        sns.barplot(data=pareto_df, x=category_col, y="count", ax=ax1, color=PALETTE["primary"])
        ax1.set_ylabel("Count")
        plt.xticks(rotation=45, ha="right")

        ax2 = ax1.twinx()
        ax2.plot(pareto_df[category_col], pareto_df["cumulative_pct"], color=PALETTE["danger"],
                  marker="o")
        ax2.axhline(80, color="gray", linestyle="--")
        ax2.set_ylabel("Cumulative %")
        ax2.set_ylim(0, 105)

        ax1.set_title(title)
        fig.tight_layout()
        out_path = Path(out_path)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    @staticmethod
    def save_static_heatmap(
        pivot_df: pd.DataFrame, out_path: str | Path, title: str = "", cmap: str = "RdYlGn",
    ) -> Path:
        """Save a static PNG heatmap via Seaborn."""
        fig, ax = plt.subplots(figsize=(9, 5))
        sns.heatmap(pivot_df, annot=True, fmt=".2f", cmap=cmap, ax=ax, linewidths=0.5)
        ax.set_title(title)
        fig.tight_layout()
        out_path = Path(out_path)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    @staticmethod
    def save_static_box_chart(
        df: pd.DataFrame, x: str, y: str, out_path: str | Path, title: str = "",
    ) -> Path:
        """Save a static PNG box plot via Seaborn."""
        fig, ax = plt.subplots(figsize=(9, 4.5))
        sns.boxplot(data=df, x=x, y=y, hue=x, ax=ax, palette="deep", legend=False)
        ax.set_title(title)
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        out_path = Path(out_path)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path
