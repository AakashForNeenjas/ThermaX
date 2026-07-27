import argparse
import os
import logging

import plotly.graph_objects as go
import plotly.express as px

from ..config import load_component_configs, DEFAULT_THRESHOLD_TEMP
from ..io.excel_loader import load_thermal_run
from ..io.batch_loader import load_campaign_from_folder
from ..analysis.stats import compute_component_stats
from ..analysis.thresholds import evaluate_limits
from ..analysis.steady_state import detect_steady_state
from ..analysis.comparisons import compare_component_across_runs, get_worst_case_components
from ..reporting.excel_export import export_run_summary_to_excel
from ..reporting.html_report import generate_html_report_for_run, generate_section_html_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _build_timeseries_fig(run, components, configs) -> go.Figure:
    """Create a Plotly time-series figure for the given components."""
    fig = go.Figure()
    if run.timestamps is not None and not run.timestamps.isna().all():
        x = run.timestamps
        x_label = "Time"
    else:
        x = run.time / 60.0
        x_label = "Time (min)"

    for comp in components:
        if comp not in run.data.columns:
            continue
        cfg = configs.get(comp)
        color = cfg.color_hint if cfg and cfg.color_hint else None
        fig.add_trace(go.Scatter(x=x, y=run.data[comp], mode="lines",
                                 name=comp, line=dict(color=color) if color else {}))
        if cfg:
            fig.add_hline(y=cfg.max_limit, line_dash="dash", line_color="red",
                          annotation_text=f"{comp} limit")

    fig.update_layout(xaxis_title=x_label, yaxis_title="Temperature (°C)",
                      title=f"Time Series — {run.run_id}", hovermode="x unified")
    return fig


def _build_bar_fig(run, stats, top_n=20) -> go.Figure:
    df = stats.sort_values("max_temp", ascending=False).head(top_n)
    fig = px.bar(df, x="component", y="max_temp", color="max_temp",
                 color_continuous_scale="RdYlBu_r",
                 title=f"Top {top_n} Max Temperatures — {run.run_id}",
                 labels={"max_temp": "Max Temp (°C)"})
    fig.update_layout(xaxis_tickangle=-45)
    return fig


def analyze_run(args):
    """Analyze a single run."""
    logger.info(f"Analyzing run: {args.file}")

    configs = {}
    if args.components_config:
        configs = load_component_configs(args.components_config)

    try:
        run = load_thermal_run(args.file, configs)
    except Exception as e:
        logger.error(f"Failed to load run: {e}")
        return

    run_output_dir = os.path.join(args.output_dir, run.run_id)
    _ensure_dir(run_output_dir)

    stats = compute_component_stats(run, threshold_temp=DEFAULT_THRESHOLD_TEMP)
    limits = evaluate_limits(run, configs, stats=stats)
    steady = detect_steady_state(run)

    # Plotly figures
    top5 = stats.sort_values("max_temp", ascending=False).head(5)["component"].tolist()
    fig_ts = _build_timeseries_fig(run, top5, configs)
    fig_bar = _build_bar_fig(run, stats)

    # Reports
    excel_path = os.path.join(run_output_dir, f"{run.run_id}_report.xlsx")
    export_run_summary_to_excel(run, stats, limits, steady, excel_path)

    stats.to_csv(os.path.join(run_output_dir, f"{run.run_id}_component_stats.csv"), index=False)
    limits.to_csv(os.path.join(run_output_dir, f"{run.run_id}_limit_eval.csv"), index=False)

    html_path = os.path.join(run_output_dir, f"{run.run_id}_report.html")
    generate_html_report_for_run(
        run, stats, limits, steady,
        plotly_figs=[fig_ts, fig_bar],
        output_path=html_path,
    )

    # Terminal summary
    print("\n=== Analysis Summary ===")
    print(f"Run ID: {run.run_id}")
    print(f"Steady State: {steady['steady']}")
    print("\nTop 5 Hottest Components:")
    print(stats.sort_values("max_temp", ascending=False).head(5)[["component", "max_temp"]])
    failures = limits[limits["status"] == "FAIL"]
    if not failures.empty:
        print("\nCRITICAL FAILURES:")
        print(failures[["component", "max_temp", "max_limit"]])
    else:
        print("\nNo critical failures detected.")

    logger.info(f"Analysis complete. Reports in: {run_output_dir}")


def analyze_folder(args):
    """Analyze a whole folder (campaign)."""
    logger.info(f"Analyzing folder: {args.folder}")

    configs = {}
    if args.components_config:
        configs = load_component_configs(args.components_config)

    campaign = load_campaign_from_folder(args.folder, configs)
    _ensure_dir(args.output_dir)

    worst = get_worst_case_components(campaign, configs)
    worst.to_excel(os.path.join(args.output_dir, "campaign_worst_case.xlsx"), index=False)
    worst.to_csv(os.path.join(args.output_dir, "campaign_worst_case.csv"), index=False)

    # Campaign overview Plotly chart
    fig = px.scatter(worst, x="run_id", y="max_temp", color="component", size="max_temp",
                     hover_data=["margin"],
                     title="Worst Case Components — Campaign Overview")

    sections = [
        {
            "header": "Worst Case Components",
            "content": f"Top hottest component–run combinations across {len(campaign.runs)} runs.",
            "dataframe": worst,
            "plotly_fig": fig,
        }
    ]
    generate_section_html_report(
        f"Campaign Report — {os.path.basename(args.folder)}",
        sections,
        output_path=os.path.join(args.output_dir, "campaign_report.html"),
    )

    print("\n=== Campaign Summary ===")
    print(f"Total Runs: {len(campaign.runs)}")
    print("Worst Case Components (Top 5):")
    print(worst.head(5)[["run_id", "component", "max_temp", "margin"]])
    logger.info(f"Campaign analysis saved to {args.output_dir}")


def compare_component(args):
    """Compare a component across runs."""
    logger.info(f"Comparing component: {args.component}")

    configs = {}
    if args.components_config:
        configs = load_component_configs(args.components_config)

    campaign = load_campaign_from_folder(args.folder, configs)
    _ensure_dir(args.output_dir)

    df = compare_component_across_runs(campaign, args.component)
    if df.empty:
        logger.warning(f"Component {args.component} not found in any runs.")
        return

    # Build Plotly trend figure
    fig = px.line(df, x="run_id", y="max_temp", markers=True,
                  title=f"Max Temp of {args.component} across runs",
                  hover_data=df.columns)
    cfg = configs.get(args.component)
    if cfg:
        fig.add_hline(y=cfg.max_limit, line_dash="dash", line_color="red",
                      annotation_text="Max Limit")

    df.to_excel(os.path.join(args.output_dir, f"compare_{args.component}.xlsx"), index=False)
    df.to_csv(os.path.join(args.output_dir, f"compare_{args.component}.csv"), index=False)

    sections = [
        {
            "header": f"Temperature Trend: {args.component}",
            "content": f"Max temperatures for {args.component} across {len(df)} runs.",
            "dataframe": df,
            "plotly_fig": fig,
        }
    ]
    generate_section_html_report(
        f"Component Comparison: {args.component}",
        sections,
        output_path=os.path.join(args.output_dir, f"compare_{args.component}_report.html"),
    )

    print(f"\nComparison for {args.component} saved to {args.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Thermal Test Campaign Analyzer")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("analyze-run", help="Analyze a single Excel file")
    p_run.add_argument("file")
    p_run.add_argument("--components-config")
    p_run.add_argument("--output-dir", default="out")

    p_folder = sub.add_parser("analyze-folder", help="Analyze a folder of Excel files")
    p_folder.add_argument("folder")
    p_folder.add_argument("--components-config")
    p_folder.add_argument("--output-dir", default="out")

    p_comp = sub.add_parser("compare-component", help="Compare a component across runs")
    p_comp.add_argument("component")
    p_comp.add_argument("--folder", required=True)
    p_comp.add_argument("--components-config")
    p_comp.add_argument("--output-dir", default="out")

    args = parser.parse_args()
    if args.command == "analyze-run":
        analyze_run(args)
    elif args.command == "analyze-folder":
        analyze_folder(args)
    elif args.command == "compare-component":
        compare_component(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
