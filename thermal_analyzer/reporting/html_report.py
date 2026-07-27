"""
HTML report generation — handles both single-run detailed reports and
generic section-based reports (replaces the old generic_report.py).

Plotly figures are embedded as interactive HTML; no matplotlib dependency.
Reports include print-friendly CSS so File → Print → Save as PDF works well.
"""
import os
import pandas as pd
from typing import Any, Dict, List, Optional, Union

_COMMON_CSS = """
<style>
  /* ── base ── */
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0; padding: 20px;
    background-color: #f4f4f9; color: #333;
  }
  .container {
    max-width: 1100px; margin: auto; background: white;
    padding: 40px; box-shadow: 0 0 15px rgba(0,0,0,0.1);
  }
  h1 {
    color: #2c3e50; border-bottom: 3px solid #3498db;
    padding-bottom: 10px; margin-bottom: 20px;
  }
  h2 {
    color: #2c3e50; margin-top: 30px;
    border-left: 5px solid #3498db; padding-left: 10px;
  }
  /* ── tables ── */
  table {
    border-collapse: collapse; width: 100%;
    margin-bottom: 20px; font-size: 13px;
  }
  th, td { border: 1px solid #dfe6e9; padding: 8px 10px; text-align: left; }
  th { background-color: #f1f2f6; color: #2c3e50; font-weight: 600; }
  tr:nth-child(even) { background-color: #f8f9fa; }
  /* ── status badges ── */
  .status-FAIL    { color: #d63031; font-weight: bold; }
  .status-WARNING { color: #e67e22; font-weight: bold; }
  .status-OK      { color: #00b894; font-weight: bold; }
  /* ── metadata grid ── */
  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 10px; margin-bottom: 20px;
  }
  .meta-item { background: #f1f2f6; padding: 10px; border-radius: 5px; }
  .meta-label { font-weight: bold; font-size: 11px; color: #7f8c8d; display: block; }
  .meta-value { font-size: 15px; color: #2d3436; }
  /* ── plotly container ── */
  .chart-container { margin: 20px 0; }
  /* ── print button ── */
  .print-btn {
    background: #3498db; color: white; border: none;
    padding: 10px 22px; border-radius: 5px; cursor: pointer;
    font-size: 14px; margin: 10px 0 20px 0;
  }
  .print-btn:hover { background: #2980b9; }
  /* ── print media ── */
  @media print {
    .print-btn { display: none; }
    body { background: white; padding: 0; }
    .container { box-shadow: none; padding: 0; }
    .chart-container { page-break-inside: avoid; }
  }
</style>
"""

_PLOTLY_CDN = (
    '<script src="https://cdn.plot.ly/plotly-2.32.0.min.js" '
    'charset="utf-8"></script>'
)


def _embed_plotly_fig(fig, first: bool = False) -> str:
    """Return the HTML snippet for a single Plotly figure."""
    try:
        html = fig.to_html(
            include_plotlyjs="cdn" if first else False,
            full_html=False,
            config={"responsive": True},
        )
        return f'<div class="chart-container">{html}</div>'
    except Exception:
        return ""


def generate_html_report_for_run(
    run,
    component_stats: pd.DataFrame,
    limit_eval: pd.DataFrame,
    steady_state_info: Dict[str, Any],
    plots_paths: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    plotly_figs: Optional[list] = None,
) -> str:
    """
    Generate a professional HTML report for a single thermal run.

    Parameters
    ----------
    run               : ThermalRun
    component_stats   : DataFrame from compute_component_stats()
    limit_eval        : DataFrame from evaluate_limits()
    steady_state_info : dict from detect_steady_state()
    plots_paths       : (legacy) list of image file paths to embed as base64
    output_path       : if given, write the HTML to this path
    plotly_figs       : list of plotly Figure objects to embed interactively

    Returns
    -------
    HTML string
    """
    has_plotly = bool(plotly_figs)
    html: List[str] = []
    html.append(
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'>"
        f"<title>Thermal Report: {run.run_id}</title>"
        f"{_COMMON_CSS}"
        f"{'<!-- Plotly loaded per-figure -->' if has_plotly else ''}"
        f"</head><body>"
    )
    html.append("<div class='container'>")
    html.append(
        "<button class='print-btn' onclick='window.print()'>🖨️ Print / Save as PDF</button>"
    )
    html.append(f"<h1>Thermal Test Report: {run.run_id}</h1>")

    # ── Metadata grid ──────────────────────────────────────────────────────────
    html.append("<h2>Test Conditions</h2>")
    html.append("<div class='metadata-grid'>")
    for k, v in run.metadata.items():
        html.append(
            f"<div class='meta-item'>"
            f"<span class='meta-label'>{k.upper()}</span>"
            f"<span class='meta-value'>{v}</span></div>"
        )
    ss_status = "ACHIEVED" if steady_state_info.get("steady") else "NOT REACHED"
    ss_color = "green" if steady_state_info.get("steady") else "red"
    html.append(
        f"<div class='meta-item' style='border-left:5px solid {ss_color}'>"
        f"<span class='meta-label'>STEADY STATE</span>"
        f"<span class='meta-value'>{ss_status}</span></div>"
    )
    if not steady_state_info.get("steady"):
        reason = steady_state_info.get("reason", "")
        html.append(
            f"<div style='grid-column:1/-1;color:red;margin-top:5px'><em>{reason}</em></div>"
        )
    html.append("</div>")

    # Notes
    if run.notes:
        html.append(f"<p><strong>Notes:</strong> {run.notes}</p>")

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    total = len(component_stats) if component_stats is not None else 0
    max_temp = (
        float(component_stats["max_temp"].max())
        if component_stats is not None and not component_stats.empty and "max_temp" in component_stats
        else None
    )
    fail_c = warn_c = 0
    if limit_eval is not None and not limit_eval.empty and "status" in limit_eval:
        fail_c = int((limit_eval["status"] == "FAIL").sum())
        warn_c = int((limit_eval["status"] == "WARNING").sum())

    html.append("<h2>Summary</h2>")
    html.append("<div class='metadata-grid'>")
    html.append(
        f"<div class='meta-item'><span class='meta-label'>COMPONENTS</span>"
        f"<span class='meta-value'>{total}</span></div>"
    )
    html.append(
        f"<div class='meta-item'><span class='meta-label'>FAILURES</span>"
        f"<span class='meta-value' style='color:{'red' if fail_c else 'inherit'}'>{fail_c}</span></div>"
    )
    html.append(
        f"<div class='meta-item'><span class='meta-label'>WARNINGS</span>"
        f"<span class='meta-value' style='color:{'orange' if warn_c else 'inherit'}'>{warn_c}</span></div>"
    )
    if max_temp is not None:
        html.append(
            f"<div class='meta-item'><span class='meta-label'>MAX TEMP</span>"
            f"<span class='meta-value'>{max_temp:.1f} °C</span></div>"
        )
    html.append("</div>")

    # ── Plots (Plotly preferred, legacy base64 fallback) ───────────────────────
    html.append("<h2>Thermal Analysis Charts</h2>")
    if plotly_figs:
        for i, fig in enumerate(plotly_figs):
            html.append(_embed_plotly_fig(fig, first=(i == 0)))
    elif plots_paths:
        import base64

        html.append(_PLOTLY_CDN)  # not needed but harmless placeholder
        for p_path in plots_paths:
            if os.path.exists(p_path):
                with open(p_path, "rb") as fh:
                    enc = base64.b64encode(fh.read()).decode()
                mime = "image/jpeg" if p_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
                html.append(
                    f"<div class='chart-container'>"
                    f"<img src='data:{mime};base64,{enc}' alt='Plot' style='max-width:100%'>"
                    f"</div>"
                )

    # ── Limit evaluation ───────────────────────────────────────────────────────
    html.append("<h2>Limit Evaluation</h2>")
    if limit_eval is not None and not limit_eval.empty:
        lc = limit_eval.copy()
        all_cols = list(lc.columns)
        first_cols = [c for c in ["component"] if c in all_cols]
        last_cols = [c for c in ["status"] if c in all_cols]
        middle = [c for c in all_cols if c not in first_cols + last_cols]
        lc = lc[first_cols + middle + last_cols]
        if "status" in lc.columns:
            lc["status"] = lc["status"].apply(
                lambda s: f'<span class="status-{s}">{s}</span>'
            )
        for col in lc.select_dtypes(include=["float", "float64"]).columns:
            lc[col] = lc[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "—")
        html.append(lc.to_html(escape=False, index=False, classes="table"))
    else:
        html.append("<p>No limit data available.</p>")

    # ── Component statistics appendix ──────────────────────────────────────────
    html.append("<h2>Component Statistics (Appendix)</h2>")
    if component_stats is not None and not component_stats.empty:
        sc = component_stats.copy()
        for col in sc.select_dtypes(include=["float"]).columns:
            sc[col] = sc[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
        html.append(sc.to_html(index=False, classes="table"))

    html.append("</div></body></html>")
    result = "\n".join(html)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Generic section-based report builder (replaces generic_report.py)
# ──────────────────────────────────────────────────────────────────────────────

def generate_section_html_report(
    title: str,
    sections: List[dict],
    output_path: Optional[str] = None,
) -> str:
    """
    Build a multi-section HTML report.

    Each section dict may contain:
      'header'     – section heading (str)
      'content'    – paragraph text (str)
      'dataframe'  – pd.DataFrame to render as table
      'plotly_fig' – plotly Figure to embed interactively
      'plot_path'  – (legacy) path to image file

    Returns the HTML string and optionally writes it to output_path.
    """
    html: List[str] = []
    html.append(
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'>"
        f"<title>{title}</title>"
        f"{_COMMON_CSS}"
        f"</head><body>"
    )
    html.append("<div class='container'>")
    html.append(
        "<button class='print-btn' onclick='window.print()'>🖨️ Print / Save as PDF</button>"
    )
    html.append(f"<h1>{title}</h1>")

    first_plotly = True
    for section in sections:
        if section.get("header"):
            html.append(f"<h2>{section['header']}</h2>")
        if section.get("content"):
            html.append(f"<p>{section['content']}</p>")

        # Plotly figure
        if section.get("plotly_fig") is not None:
            html.append(_embed_plotly_fig(section["plotly_fig"], first=first_plotly))
            first_plotly = False

        # Legacy: image file path
        p_path = section.get("plot_path")
        if p_path and os.path.exists(p_path):
            import base64

            with open(p_path, "rb") as fh:
                enc = base64.b64encode(fh.read()).decode()
            mime = "image/jpeg" if p_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
            html.append(
                f"<div class='chart-container'>"
                f"<img src='data:{mime};base64,{enc}' style='max-width:100%' alt='Plot'>"
                f"</div>"
            )

        df: Optional[pd.DataFrame] = section.get("dataframe")
        if df is not None and not df.empty:
            fc = df.copy()
            for col in fc.select_dtypes(include=["float", "float64"]).columns:
                fc[col] = fc[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "—")
            html.append(fc.to_html(index=False, classes="table", escape=False))

    html.append("</div></body></html>")
    result = "\n".join(html)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result


# Backward-compat alias kept so any external callers still work
def generate_generic_html_report(
    title: str,
    sections: List[dict],
    output_path: str,
) -> None:
    """Deprecated alias — use generate_section_html_report() instead."""
    generate_section_html_report(title, sections, output_path)
