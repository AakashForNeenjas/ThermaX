"""ThermaX Streamlit Dashboard — all analysis modes in one file."""
import hashlib
import io
import json
import os
import re
import shutil
import sys
import zipfile

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Tk is only used for native folder dialogs in the packaged desktop app.
# Streamlit Community Cloud runs in a headless Linux environment where
# Python's optional _tkinter extension is not installed.
try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = None
    filedialog = None

try:
    from thermal_analyzer.config import load_component_configs, DEFAULT_TIME_COLUMN
    from thermal_analyzer.io.excel_loader import load_thermal_run_from_bytes
    from thermal_analyzer.io.batch_loader import load_campaign_from_folder
    from thermal_analyzer.models import TestCampaign
    from thermal_analyzer.analysis.stats import compute_component_stats
    from thermal_analyzer.analysis.thresholds import evaluate_limits
    from thermal_analyzer.analysis.steady_state import detect_steady_state
    from thermal_analyzer.analysis.comparisons import compare_component_across_runs, get_worst_case_components
    from thermal_analyzer.analysis.physics import compute_thermal_resistance, compute_time_constants
    from thermal_analyzer.analysis.normalization import normalize_to_ambient, compute_derating_curve
    from thermal_analyzer.analysis.phase_analysis import compute_phase_stats
    from thermal_analyzer.analysis.anomaly import detect_anomalies, detect_flat_sensors
    from thermal_analyzer.utils.naming import parse_metadata_from_filename
    from thermal_analyzer.reporting.html_report import (
        generate_html_report_for_run,
        generate_section_html_report,
    )
    from thermal_analyzer.reporting.excel_export import export_run_summary_to_excel
except Exception as _import_err:
    help_msg = (
        "Failed to import the local 'thermal_analyzer' package.\n"
        "Run from the repo root:\n"
        "  .venv\\Scripts\\python.exe -m pip install -e .\n\n"
        f"Original error: {_import_err!s}"
    )
    try:
        st.error(help_msg)
    except Exception:
        print(help_msg, file=sys.stderr)
    raise

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="ThermaX Dashboard", layout="wide")
st.title("ThermaX: Thermal Analysis Dashboard")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Configuration")


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))


def _bundle_base_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.abspath("."))


def _default_dev_config_path() -> str:
    base_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    return os.path.join(base_dir, "config", "components.csv")


def _ensure_packaged_user_config() -> str:
    bundled_cfg = os.path.join(_bundle_base_dir(), "config", "components.csv")
    exe_cfg = os.path.join(os.path.dirname(sys.executable), "config", "components.csv")
    if os.path.exists(exe_cfg):
        return exe_cfg

    if os.path.exists(bundled_cfg):
        try:
            os.makedirs(os.path.dirname(exe_cfg), exist_ok=True)
            shutil.copy2(bundled_cfg, exe_cfg)
            return exe_cfg
        except Exception:
            pass

        try:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            user_cfg = os.path.join(base, "ThermaX", "config", "components.csv")
            os.makedirs(os.path.dirname(user_cfg), exist_ok=True)
            shutil.copy2(bundled_cfg, user_cfg)
            return user_cfg
        except Exception:
            pass

        return bundled_cfg

    return exe_cfg


def _normalize_config_path(raw_path: str) -> str:
    value = (raw_path or "").strip()
    if not value:
        value = _ensure_packaged_user_config() if _is_frozen_app() else _default_dev_config_path()

    value = os.path.normpath(value)

    if os.path.isdir(value):
        csv_candidate = os.path.join(value, "components.csv")
        json_candidate = os.path.join(value, "components.json")
        if os.path.exists(csv_candidate):
            return csv_candidate
        if os.path.exists(json_candidate):
            return json_candidate
        raise ValueError(f"Path points to a folder without components.csv/components.json: {value}")

    # If running from a bundled _internal path, prefer a writable sibling config path.
    norm_lower = os.path.normcase(value).lower()
    internal_cfg_suffix = os.path.normcase(os.path.join("_internal", "config", "components.csv")).lower()
    if norm_lower.endswith(internal_cfg_suffix):
        writable_cfg = os.path.join(os.path.dirname(sys.executable), "config", "components.csv")
        if not os.path.exists(writable_cfg) and os.path.exists(value):
            try:
                os.makedirs(os.path.dirname(writable_cfg), exist_ok=True)
                shutil.copy2(value, writable_cfg)
            except Exception:
                pass
        if os.path.exists(writable_cfg):
            return os.path.normpath(writable_cfg)

    return value


default_config_value = _ensure_packaged_user_config() if _is_frozen_app() else _default_dev_config_path()
config_path_input = st.sidebar.text_input("Components Config Path", value=default_config_value)
try:
    config_path = _normalize_config_path(config_path_input)
except Exception as _cfg_path_err:
    config_path = default_config_value
    st.sidebar.error(f"Invalid config path: {_cfg_path_err}")


@st.cache_data
def get_configs(path, _mtime):
    return load_component_configs(path)


@st.cache_data(show_spinner=False)
def load_run_and_stats(file_bytes, file_name, time_column):
    run = load_thermal_run_from_bytes(file_bytes, file_name, {}, time_column)
    run.run_id = os.path.splitext(file_name)[0]
    run.metadata = parse_metadata_from_filename(run.run_id)
    stats = compute_component_stats(run)
    return run, stats


def _get_session_cache(name):
    if name not in st.session_state:
        st.session_state[name] = {}
    return st.session_state[name]


def get_limits_cached(run, stats, cfgs, cache_key):
    cache = _get_session_cache("limits_cache")
    if cache_key not in cache:
        cache[cache_key] = evaluate_limits(run, cfgs, stats=stats)
    return cache[cache_key]


def get_steady_cached(run, win, slope, cache_key):
    cache = _get_session_cache("steady_cache")
    if cache_key not in cache:
        cache[cache_key] = detect_steady_state(run, window_minutes=win, slope_threshold=slope)
    return cache[cache_key]


# ── Folder picker helpers ──────────────────────────────────────────────────────
def _folder_dialog_available() -> bool:
    if tk is None or filedialog is None:
        return False
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def pick_folder(session_key: str):
    if not _folder_dialog_available():
        st.error(
            "Native folder browsing is unavailable in this cloud environment. "
            "Upload files through a file-upload control or enter a path that "
            "exists on the server."
        )
        return

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        selected = filedialog.askdirectory(master=root, title="Select folder")
    except Exception as exc:
        st.error(f"Unable to open the native folder dialog: {exc}")
        return
    finally:
        if root is not None:
            root.destroy()

    if selected:
        st.session_state[session_key] = selected
        st.rerun()


def folder_picker_widget(label: str, session_key: str) -> str:
    col_in, col_btn = st.columns([5, 1])
    with col_in:
        path = st.text_input(
            label, value=st.session_state.get(session_key, ""),
            key=f"{session_key}_text", placeholder="Type a path or click Browse →",
        )
        if path:
            st.session_state[session_key] = path
    with col_btn:
        st.write("")
        if st.button(
            "Browse",
            key=f"{session_key}_btn",
            disabled=not _folder_dialog_available(),
            help=(
                "Native folder browsing is available in the desktop app only."
                if not _folder_dialog_available()
                else None
            ),
        ):
            pick_folder(session_key)
    if not _folder_dialog_available():
        st.caption(
            "Folder browsing is disabled on Community Cloud because it cannot "
            "access folders on your computer."
        )
    return st.session_state.get(session_key, "")


# ── Inline run-matching (replaces matching.py) ────────────────────────────────
def match_runs_by_metadata(campaign_a, campaign_b):
    """Match runs from two campaigns by operating conditions."""
    _KEYS = {"VAC", "HV", "LV_current", "ambient_temp"}

    def sig(run):
        keys = sorted(k for k in run.metadata if k in _KEYS)
        return "|".join(f"{k}={run.metadata[k]}" for k in keys)

    map_b = {sig(r): r for r in campaign_b.runs if sig(r)}
    return [(ra, map_b[sig(ra)]) for ra in campaign_a.runs if sig(ra) in map_b]


# ── Global Defaults editor helpers ────────────────────────────────────────────
_GLOBAL_DEFAULTS_SPEC = {
    "DEFAULT_TIME_COLUMN":    {"type": "str",   "label": "Time Column Name",              "help": "Excel column used as the time axis"},
    "DEFAULT_MAX_LIMIT":      {"type": "float", "label": "Fallback Max Limit (°C)",       "help": "FAIL threshold for components not in components.csv"},
    "DEFAULT_WARNING_LIMIT":  {"type": "float", "label": "Fallback Warning Limit (°C)",   "help": "WARNING threshold for components not in components.csv"},
    "DEFAULT_CRITICAL_LIMIT": {"type": "float", "label": "Fallback Critical Limit (°C)",  "help": "Critical threshold for components not in components.csv"},
    "DEFAULT_THRESHOLD_TEMP": {"type": "float", "label": "Threshold Temp for Stats (°C)", "help": "Temperature used for the time-to-XC column in component stats"},
}


def _read_global_defaults(config_file: str) -> dict:
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
    values = {}
    for key, spec in _GLOBAL_DEFAULTS_SPEC.items():
        if spec["type"] == "str":
            m = re.search(rf'^{key}\s*=\s*"([^"]*)"', content, re.MULTILINE)
            values[key] = m.group(1) if m else ""
        else:
            m = re.search(rf'^{key}\s*=\s*([\d.]+)', content, re.MULTILINE)
            values[key] = float(m.group(1)) if m else 0.0
    return values


def _write_global_defaults(config_file: str, values: dict):
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
    for key, spec in _GLOBAL_DEFAULTS_SPEC.items():
        val = values[key]
        new_line = f'{key} = "{val}"' if spec["type"] == "str" else f"{key} = {float(val)}"
        content = re.sub(rf'^{key}\s*=\s*.*', new_line, content, flags=re.MULTILINE)
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(content)


# ── Sidecar JSON writer (Annotation/Notes) ────────────────────────────────────
def _save_sidecar(folder: str, run_id: str, notes: str, extra_meta: dict):
    """Write a .json sidecar next to the Excel file with notes + metadata."""
    path = os.path.join(folder, f"{run_id}.json")
    data = dict(extra_meta)
    data["notes"] = notes
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Config loading ─────────────────────────────────────────────────────────────
try:
    st.sidebar.caption(f"Using: {config_path}")
    if os.path.isdir(config_path):
        raise ValueError(f"Config path is a directory: {config_path}")
    ext = os.path.splitext(config_path)[1].lower()
    if ext not in [".csv", ".json"]:
        raise ValueError(f"Unsupported config file format '{ext or '(none)'}'. Use .csv or .json")
    mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0
    configs = get_configs(config_path, mtime)
    st.sidebar.success(f"Loaded {len(configs)} component configs.")
    if st.sidebar.checkbox("Show Debug Info"):
        st.sidebar.write("Config Keys (first 5):", list(configs.keys())[:5])
except Exception as e:
    st.sidebar.error(f"Error loading config: {e}")
    configs = {}

st.sidebar.header("Steady State Settings")
window_minutes = st.sidebar.number_input("Window Size (minutes)", min_value=1.0, value=10.0, step=1.0)
slope_threshold = st.sidebar.number_input("Slope Threshold (°C/min)", min_value=0.01, value=1.0, step=0.05)

mode = st.sidebar.radio(
    "Select Mode",
    [
        "Single Run Analysis",
        "Campaign Analysis",
        "Component Comparison",
        "Samples Comparison (A vs B)",
        "File vs File Comparison",
        "Configuration Editor",
    ],
)

# ══════════════════════════════════════════════════════════════════════════════
# MODE: Single Run Analysis
# ══════════════════════════════════════════════════════════════════════════════
if mode == "Single Run Analysis":
    st.header("Single Run Analysis")
    uploaded_file = st.file_uploader("Upload Thermal Data Excel", type=["xlsx"])

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        if not file_bytes:
            st.error("Uploaded file is empty.")
            file_bytes = None

        run = None
        try:
            if file_bytes is None:
                raise ValueError("No data to process.")

            file_hash = hashlib.sha256(file_bytes).hexdigest()
            run, stats = load_run_and_stats(file_bytes, uploaded_file.name, DEFAULT_TIME_COLUMN)

            # Metadata
            st.subheader("Metadata")
            st.json(run.metadata)

            if st.sidebar.checkbox("Show Run Components"):
                comps = run.available_components()
                st.sidebar.write("Run Components (first 5):", comps[:5])
                first = comps[0] if comps else None
                if first:
                    if first in configs:
                        st.sidebar.success(f"Match found for '{first}'")
                    else:
                        st.sidebar.error(f"No config match for '{first}'")

            # Limits & steady-state
            limits_key = (file_hash, config_path, mtime)
            limits = get_limits_cached(run, stats, configs, limits_key)
            steady_key = (file_hash, float(window_minutes), float(slope_threshold))
            steady = get_steady_cached(run, window_minutes, slope_threshold, steady_key)

            # ── KPIs ──────────────────────────────────────────────────────────
            col1, col2, col3 = st.columns(3)
            col1.metric("Max Temp", f"{stats['max_temp'].max():.1f} °C")
            col2.metric("Steady State", str(steady["steady"]))
            col3.metric("Critical Failures", len(limits[limits["status"] == "FAIL"]))

            if not steady["steady"]:
                st.warning(steady.get("reason", "Steady state not reached."))
                slopes = steady.get("slopes_per_min", {})
                if slopes:
                    slope_df = (
                        pd.DataFrame(list(slopes.items()), columns=["Component", "Slope (°C/min)"])
                        .assign(**{"Abs Slope": lambda d: d["Slope (°C/min)"].abs()})
                        .sort_values("Abs Slope", ascending=False)
                        .drop(columns=["Abs Slope"])
                    )
                    st.dataframe(slope_df)
            else:
                st.success(f"Steady state reached at {steady.get('t_steady_state', 0):.1f} s")
                with st.expander("Steady State Details"):
                    slopes = steady.get("slopes_per_min", {})
                    slope_df = (
                        pd.DataFrame(list(slopes.items()), columns=["Component", "Slope (°C/min)"])
                        .assign(**{"Abs Slope": lambda d: d["Slope (°C/min)"].abs()})
                        .sort_values("Abs Slope", ascending=False)
                        .drop(columns=["Abs Slope"])
                    )
                    st.dataframe(slope_df)

            # ── Component Group Filter ─────────────────────────────────────────
            all_groups = sorted({cfgs.group for cfgs in configs.values()}) if configs else []
            group_filter = st.multiselect(
                "Filter components by group",
                options=["(all)"] + all_groups,
                default=["(all)"],
                key="sra_group_filter",
            )
            all_comps = run.available_components()
            if "(all)" not in group_filter and all_groups:
                filtered_comps = [
                    c for c in all_comps
                    if configs.get(c) and configs[c].group in group_filter
                ]
            else:
                filtered_comps = all_comps

            # ── Time Series ───────────────────────────────────────────────────
            st.subheader("Temperature vs Time")
            if run.timestamps is not None and not run.timestamps.isna().all():
                x_axis, x_label = run.timestamps, "Time"
            else:
                x_axis, x_label = run.time / 60.0, "Time (min)"

            top5 = stats.sort_values("max_temp", ascending=False).head(5)["component"].tolist()
            default_sel = [c for c in top5 if c in filtered_comps][:5]
            selected_comps = st.multiselect(
                "Select Components to Plot", filtered_comps, default=default_sel, key="sra_ts_sel"
            )

            fig_ts = go.Figure()
            for comp in selected_comps:
                fig_ts.add_trace(go.Scatter(x=x_axis, y=run.data[comp], mode="lines", name=comp))
            fig_ts.update_layout(xaxis_title=x_label, yaxis_title="Temperature (°C)", hovermode="x unified")
            st.plotly_chart(fig_ts, use_container_width=True)

            # ── Bar Chart ─────────────────────────────────────────────────────
            st.subheader("Max Temperatures")
            top_n = st.slider("Show Top N Components", 5, min(50, len(stats)), min(20, len(stats)), key="sra_topn")
            top_stats = stats[stats["component"].isin(filtered_comps)].sort_values("max_temp", ascending=False).head(top_n)
            fig_bar = px.bar(top_stats, x="component", y="max_temp", color="max_temp",
                             title="Max Temperatures", color_continuous_scale="RdYlBu_r")
            st.plotly_chart(fig_bar, use_container_width=True)

            # ── Startup Phase Analysis (NEW) ───────────────────────────────────
            with st.expander("Startup Phase Analysis (Transient vs Main)", expanded=False):
                st.markdown(
                    "Splits the run into a **startup (transient)** phase and a **main** phase. "
                    "A large transient spike means the component runs hotter during startup than steady operation."
                )
                startup_mins = st.number_input(
                    "Startup phase duration (minutes)", min_value=0.5, value=5.0, step=0.5, key="sra_startup_mins"
                )
                phase_df = compute_phase_stats(run, startup_minutes=startup_mins)
                phase_df_filt = phase_df[phase_df["component"].isin(filtered_comps)]

                def color_spike(val):
                    if pd.isna(val):
                        return ""
                    if val > 10:
                        return "color: red; font-weight: bold"
                    if val > 5:
                        return "color: orange"
                    return "color: green"

                st.dataframe(
                    phase_df_filt.style.map(color_spike, subset=["transient_spike (°C)"]).format(
                        {"startup_max (°C)": "{:.1f}", "main_max (°C)": "{:.1f}", "transient_spike (°C)": "{:.1f}"},
                        na_rep="—",
                    ),
                    use_container_width=True,
                )
                if not phase_df_filt.empty:
                    fig_phase = go.Figure()
                    fig_phase.add_trace(
                        go.Bar(name="Startup Max", x=phase_df_filt["component"],
                               y=phase_df_filt["startup_max (°C)"], marker_color="tomato")
                    )
                    fig_phase.add_trace(
                        go.Bar(name="Main Phase Max", x=phase_df_filt["component"],
                               y=phase_df_filt["main_max (°C)"], marker_color="steelblue")
                    )
                    fig_phase.update_layout(barmode="group", xaxis_tickangle=-45,
                                            yaxis_title="Temperature (°C)")
                    st.plotly_chart(fig_phase, use_container_width=True)

            # ── Limit Evaluation ──────────────────────────────────────────────
            st.subheader("Limit Evaluation")

            def color_status(val):
                c = "red" if val == "FAIL" else ("orange" if val == "WARNING" else "green")
                return f"color: {c}; font-weight: bold"

            limits_filt = limits[limits["component"].isin(filtered_comps)] if "component" in limits.columns else limits
            st.dataframe(limits_filt.style.map(color_status, subset=["status"]), use_container_width=True)

            # ── Design Margin View (NEW) ───────────────────────────────────────
            with st.expander("Design Margin View", expanded=False):
                st.markdown(
                    "Shows how far each component is from its limit — as both an absolute margin and a percentage. "
                    "Negative margin means the limit has been exceeded."
                )
                if not limits.empty and "max_limit" in limits.columns:
                    margin_df = limits[["component", "max_temp", "max_limit", "warning_limit"]].copy()
                    margin_df["margin_to_max (°C)"] = margin_df["max_limit"] - margin_df["max_temp"]
                    margin_df["margin_pct"] = (margin_df["margin_to_max (°C)"] / margin_df["max_limit"] * 100).round(1)
                    margin_df = margin_df[margin_df["component"].isin(filtered_comps)].sort_values("margin_to_max (°C)")

                    def color_margin(val):
                        if pd.isna(val):
                            return ""
                        if val < 0:
                            return "color: red; font-weight: bold"
                        if val < 10:
                            return "color: orange"
                        return "color: green"

                    st.dataframe(
                        margin_df.style.map(color_margin, subset=["margin_to_max (°C)", "margin_pct"]).format(
                            {"max_temp": "{:.1f}", "max_limit": "{:.1f}",
                             "warning_limit": "{:.1f}", "margin_to_max (°C)": "{:.1f}",
                             "margin_pct": "{:.1f}%"}
                        ),
                        use_container_width=True,
                    )
                    # Gauge-style bar chart
                    fig_margin = px.bar(
                        margin_df, x="component", y="margin_to_max (°C)",
                        color="margin_to_max (°C)", color_continuous_scale="RdYlGn",
                        title="Design Margin to Max Limit (°C) — higher is safer",
                    )
                    fig_margin.add_hline(y=0, line_dash="dash", line_color="red")
                    fig_margin.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_margin, use_container_width=True)

            # ── Ambient Normalization (NEW) ────────────────────────────────────
            with st.expander("Ambient Temperature Normalization", expanded=False):
                st.markdown(
                    "Shift all temperatures to a reference ambient so results from "
                    "runs at different room temperatures are directly comparable."
                )
                n_col1, n_col2 = st.columns(2)
                measured_amb = n_col1.number_input(
                    "Measured Ambient (°C)", value=float(run.metadata.get("ambient_temp", 25.0)),
                    step=1.0, key="sra_meas_amb"
                )
                ref_amb = n_col2.number_input(
                    "Reference Ambient (°C)", value=25.0, step=1.0, key="sra_ref_amb"
                )
                norm_df = normalize_to_ambient(stats, measured_amb, ref_amb)
                norm_show = norm_df[["component", "max_temp", "max_temp_norm", "offset_applied"]].copy()
                norm_show = norm_show[norm_show["component"].isin(filtered_comps)]
                st.dataframe(
                    norm_show.style.format({"max_temp": "{:.1f}", "max_temp_norm": "{:.1f}", "offset_applied": "{:+.1f}"}),
                    use_container_width=True,
                )
                st.download_button(
                    "Download Normalized Stats (CSV)", norm_df.to_csv(index=False),
                    file_name=f"{run.run_id}_normalized.csv", mime="text/csv", key="sra_norm_dl"
                )

            # ── Physics Metrics ────────────────────────────────────────────────
            with st.expander("Physics Metrics (ΔT & R_th)", expanded=False):
                default_amb = float(run.metadata.get("ambient_temp", 25.0))
                p1, p2 = st.columns(2)
                ambient_input = p1.number_input("Ambient Temp (°C)", value=default_amb, key="sra_amb")
                power_input = p2.number_input("Est. Power Loss (W)", value=0.0, key="sra_pwr",
                                               help="Total power to compute R_th")
                phys_df = compute_thermal_resistance(run, power_input, ambient_input)
                tau_df = compute_time_constants(run)
                if not tau_df.empty:
                    phys_df = pd.merge(phys_df, tau_df, on="component", how="left")
                st.dataframe(phys_df.style.format({
                    "max_temp": "{:.2f}", "delta_t": "{:.2f}",
                    "R_th (°C/W)": "{:.2f}", "tau (s)": "{:.1f}", "tau (min)": "{:.2f}",
                }), use_container_width=True)
                st.info("τ = time to reach 63.2% of the final temperature rise. Low τ → fast-heating component.")

            # ── Flat Sensor Detection ─────────────────────────────────────────
            suspects = detect_flat_sensors(run)
            if suspects:
                st.warning(f"Possible disconnected/faulty sensors: {', '.join(suspects)}")

            # ── Run Notes / Annotations (NEW) ─────────────────────────────────
            with st.expander("Run Notes & Annotations", expanded=False):
                st.markdown(
                    "Add notes about this run. Use **Save Sidecar JSON** to persist them "
                    "alongside the original Excel file so they reload on the next analysis."
                )
                notes_text = st.text_area("Notes", value=run.notes or "", key="sra_notes")
                sidecar_folder = st.text_input(
                    "Folder containing the Excel file (for saving sidecar)",
                    value="", key="sra_sidecar_folder", placeholder="e.g. C:/Data/runs",
                )
                if st.button("Save Sidecar JSON", key="sra_save_sidecar"):
                    if sidecar_folder and os.path.isdir(sidecar_folder):
                        _save_sidecar(sidecar_folder, run.run_id, notes_text, run.metadata)
                        st.success(f"Saved {run.run_id}.json in {sidecar_folder}")
                    else:
                        st.error("Enter a valid folder path to save the sidecar.")

            # ── Data Exports ──────────────────────────────────────────────────
            st.subheader("Data Exports")
            c1, c2 = st.columns(2)
            c1.download_button("Component Stats (CSV)", stats.to_csv(index=False),
                               file_name=f"{run.run_id}_component_stats.csv", mime="text/csv")
            c2.download_button("Limit Evaluation (CSV)", limits.to_csv(index=False),
                               file_name=f"{run.run_id}_limit_eval.csv", mime="text/csv")

            # ── Report Generation ─────────────────────────────────────────────
            st.divider()
            if st.button("Generate Professional Report (HTML)", key="sra_gen_report"):
                html_str = generate_html_report_for_run(
                    run, stats, limits, steady,
                    plotly_figs=[fig_ts, fig_bar],
                )
                st.session_state["run_report_id"] = run.run_id
                st.session_state["run_report_html"] = html_str
                st.session_state["run_report_stats_csv"] = stats.to_csv(index=False)
                st.session_state["run_report_limits_csv"] = limits.to_csv(index=False)
                st.success("Report generated — click Download below.")

        except Exception as e:
            st.error(f"Error analysing file: {e}")

        if (
            run is not None
            and "run_report_html" in st.session_state
            and st.session_state.get("run_report_id") == run.run_id
        ):
            rid = st.session_state["run_report_id"]
            dl1, dl2, dl3 = st.columns(3)
            dl1.download_button("Download HTML Report", st.session_state["run_report_html"],
                                file_name=f"{rid}_report.html", mime="text/html")
            dl2.download_button("Download Stats CSV", st.session_state["run_report_stats_csv"],
                                file_name=f"{rid}_stats.csv", mime="text/csv")
            dl3.download_button("Download Limits CSV", st.session_state["run_report_limits_csv"],
                                file_name=f"{rid}_limits.csv", mime="text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# MODE: Campaign Analysis
# ══════════════════════════════════════════════════════════════════════════════
elif mode == "Campaign Analysis":
    st.header("Campaign Analysis")
    st.markdown("Select the folder containing all Excel run files for this campaign.")

    folder_path = folder_picker_widget("Campaign Folder", "campaign_folder_path")

    if "campaign_results" not in st.session_state:
        st.session_state["campaign_results"] = None

    if folder_path:
        if st.button("Analyze Campaign"):
            if os.path.isdir(folder_path):
                with st.spinner("Loading and analyzing files..."):
                    campaign = load_campaign_from_folder(folder_path, configs)
                    if campaign.runs:
                        worst = get_worst_case_components(campaign, configs, top_n=20)
                        st.session_state["campaign_results"] = {
                            "campaign": campaign,
                            "worst": worst,
                            "folder_name": os.path.basename(folder_path),
                            "folder_path": folder_path,
                        }
                        st.success(f"Loaded {len(campaign.runs)} runs.")
                    else:
                        st.warning("No valid Excel files found.")
            else:
                st.error("Selected path is not a valid folder.")
    else:
        st.info("Select a folder to begin.")

    if st.session_state["campaign_results"]:
        res = st.session_state["campaign_results"]
        worst = res["worst"]
        folder_name = res["folder_name"]
        campaign = res["campaign"]

        # ── Worst Case ────────────────────────────────────────────────────────
        st.subheader("Worst Case Analysis (Top 20)")
        st.dataframe(worst, use_container_width=True)
        st.download_button("Download Worst Case (CSV)", worst.to_csv(index=False),
                           file_name=f"{folder_name}_worst_case.csv", mime="text/csv")

        fig_scatter = px.scatter(
            worst, x="run_id", y="max_temp", color="component", size="max_temp",
            hover_data=["margin"], title="Worst Case Temperatures Overview",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        # ── Trend Analysis (NEW) ──────────────────────────────────────────────
        st.subheader("Trend Analysis")
        st.markdown("Track how a single component's temperature changes across all runs and conditions.")
        all_comp_names = sorted(campaign.list_components())
        trend_comp = st.selectbox("Select component for trend analysis", all_comp_names, key="ca_trend_comp")
        if trend_comp:
            trend_df = compare_component_across_runs(campaign, trend_comp)
            if not trend_df.empty:
                x_opts = [c for c in trend_df.columns if c != "run_id"]
                x_sel = st.selectbox("X-axis variable", ["run_id"] + x_opts, key="ca_trend_x")
                fig_trend = px.line(
                    trend_df, x=x_sel, y="max_temp", markers=True,
                    title=f"Max Temp of {trend_comp} across runs",
                    hover_data=trend_df.columns,
                )
                cfg = configs.get(trend_comp)
                if cfg:
                    fig_trend.add_hline(y=cfg.max_limit, line_dash="dash",
                                        line_color="red", annotation_text="Max Limit")
                    fig_trend.add_hline(y=cfg.warning_limit, line_dash="dot",
                                        line_color="orange", annotation_text="Warning Limit")
                st.plotly_chart(fig_trend, use_container_width=True)

                # Derating Curve
                if "ambient_temp" in trend_df.columns and trend_df["ambient_temp"].notna().sum() >= 2:
                    with st.expander("Thermal Derating Curve (Tmax vs Ambient)", expanded=False):
                        sum_df, curve_df = compute_derating_curve(trend_df, trend_comp)
                        if "message" not in sum_df.columns:
                            st.dataframe(sum_df, use_container_width=True)
                            fig_der = go.Figure()
                            fig_der.add_trace(
                                go.Scatter(x=trend_df["ambient_temp"], y=trend_df["max_temp"],
                                           mode="markers", name="Measured", marker=dict(size=8))
                            )
                            fig_der.add_trace(
                                go.Scatter(x=curve_df["ambient_temp"], y=curve_df["predicted_max_temp"],
                                           mode="lines", name="Linear Fit", line=dict(dash="dash", color="red"))
                            )
                            if cfg:
                                fig_der.add_hline(y=cfg.max_limit, line_dash="dash", line_color="red",
                                                  annotation_text="Max Limit")
                            fig_der.update_layout(xaxis_title="Ambient Temp (°C)",
                                                  yaxis_title="Max Temp (°C)",
                                                  title=f"Derating Curve — {trend_comp}")
                            st.plotly_chart(fig_der, use_container_width=True)
                        else:
                            st.info(sum_df.iloc[0, 0])
            else:
                st.info(f"{trend_comp} not found in any runs.")

        # ── Design Margin across Campaign (NEW) ────────────────────────────────
        with st.expander("Design Margin — Campaign Overview", expanded=False):
            st.markdown("Shows margin (max_limit − max_temp) for each component in worst-case runs.")
            if "max_temp" in worst.columns and "margin" in worst.columns:
                margin_worst = worst[["run_id", "component", "max_temp", "margin"]].copy()
                margin_worst["margin_pct"] = (margin_worst["margin"] / (margin_worst["max_temp"] + margin_worst["margin"]) * 100).round(1)
                fig_marg = px.scatter(
                    margin_worst, x="component", y="margin", color="run_id",
                    title="Design Margin per Component (worst-case runs)",
                    labels={"margin": "Margin to Max Limit (°C)"},
                )
                fig_marg.add_hline(y=0, line_dash="dash", line_color="red")
                st.plotly_chart(fig_marg, use_container_width=True)
                st.dataframe(margin_worst.sort_values("margin"), use_container_width=True)

        # ── Anomaly Detection (NEW) ────────────────────────────────────────────
        with st.expander("Anomaly & Fault Detection", expanded=False):
            st.markdown(
                "Flags runs where a component's temperature is statistically unusual "
                "(z-score method). Also checks for flat / non-responsive sensors per run."
            )
            z_thresh = st.number_input("Z-score threshold", value=2.5, step=0.1, key="ca_z_thresh")
            anomaly_df = detect_anomalies(campaign, z_threshold=z_thresh)
            if not anomaly_df.empty:
                st.warning(f"{len(anomaly_df)} anomalous reading(s) found across the campaign.")

                def color_anomaly(val):
                    if val == "UNUSUALLY HOT":
                        return "color: red; font-weight: bold"
                    if val == "UNUSUALLY COLD":
                        return "color: blue; font-weight: bold"
                    return ""

                st.dataframe(
                    anomaly_df.style.map(color_anomaly, subset=["anomaly_type"]).format(
                        {"max_temp": "{:.1f}", "campaign_mean": "{:.1f}",
                         "campaign_std": "{:.1f}", "z_score": "{:.2f}"}
                    ),
                    use_container_width=True,
                )
                st.download_button("Download Anomalies (CSV)", anomaly_df.to_csv(index=False),
                                   file_name="campaign_anomalies.csv", mime="text/csv")
            else:
                st.success("No anomalies detected at current threshold.")

            st.markdown("**Flat Sensor Check per Run:**")
            flat_records = []
            for run in campaign.runs:
                suspects = detect_flat_sensors(run)
                if suspects:
                    flat_records.append({"run_id": run.run_id, "suspect_sensors": ", ".join(suspects)})
            if flat_records:
                st.dataframe(pd.DataFrame(flat_records), use_container_width=True)
            else:
                st.success("No flat/disconnected sensors detected.")

        # ── Report Generation ─────────────────────────────────────────────────
        st.divider()
        if st.button("Generate Campaign Report (HTML)", key="ca_gen_report"):
            fig_rpt = px.scatter(
                worst, x="run_id", y="max_temp", color="component", size="max_temp",
                hover_data=["margin"], title="Worst Case Components Overview",
            )
            html_str = generate_section_html_report(
                f"Campaign: {folder_name}",
                [
                    {
                        "header": "Worst Case Components",
                        "content": f"Top hottest component–run combinations across {len(campaign.runs)} runs.",
                        "plotly_fig": fig_rpt,
                        "dataframe": worst,
                    }
                ],
            )
            st.session_state["campaign_report_html"] = html_str
            st.success("Report generated.")

        if "campaign_report_html" in st.session_state:
            st.download_button(
                "Download Campaign Report (HTML)", st.session_state["campaign_report_html"],
                file_name="campaign_report.html", mime="text/html",
            )

        # ── Batch Report Generation (NEW) ──────────────────────────────────────
        with st.expander("Batch Report Generation", expanded=False):
            st.markdown(
                "Generate individual HTML reports for **every run** in the campaign, "
                "then download them all as a single ZIP archive."
            )
            if st.button("Generate Batch Reports (ZIP)", key="ca_batch_rpt"):
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    prog = st.progress(0)
                    for i, run in enumerate(campaign.runs):
                        try:
                            run_stats = compute_component_stats(run)
                            run_limits = evaluate_limits(run, configs, stats=run_stats)
                            run_steady = detect_steady_state(
                                run, window_minutes=window_minutes, slope_threshold=slope_threshold
                            )
                            if run.timestamps is not None and not run.timestamps.isna().all():
                                x_ax, x_lbl = run.timestamps, "Time"
                            else:
                                x_ax, x_lbl = run.time / 60.0, "Time (min)"
                            top5 = run_stats.sort_values("max_temp", ascending=False).head(5)["component"].tolist()
                            fig_ts_r = go.Figure()
                            for comp in top5:
                                fig_ts_r.add_trace(go.Scatter(x=x_ax, y=run.data[comp], mode="lines", name=comp))
                            fig_ts_r.update_layout(xaxis_title=x_lbl, yaxis_title="Temperature (°C)")
                            fig_bar_r = px.bar(
                                run_stats.sort_values("max_temp", ascending=False).head(20),
                                x="component", y="max_temp", color="max_temp",
                                color_continuous_scale="RdYlBu_r",
                            )
                            html_r = generate_html_report_for_run(
                                run, run_stats, run_limits, run_steady,
                                plotly_figs=[fig_ts_r, fig_bar_r],
                            )
                            zf.writestr(f"{run.run_id}_report.html", html_r)
                        except Exception as ex:
                            zf.writestr(f"{run.run_id}_ERROR.txt", str(ex))
                        prog.progress((i + 1) / len(campaign.runs))
                zip_buf.seek(0)
                st.session_state["batch_zip"] = zip_buf.getvalue()
                st.success(f"Generated reports for {len(campaign.runs)} runs.")

            if "batch_zip" in st.session_state:
                st.download_button(
                    "Download All Reports (ZIP)", st.session_state["batch_zip"],
                    file_name=f"{folder_name}_batch_reports.zip",
                    mime="application/zip",
                )

# ══════════════════════════════════════════════════════════════════════════════
# MODE: Component Comparison
# ══════════════════════════════════════════════════════════════════════════════
elif mode == "Component Comparison":
    st.header("Component Comparison")
    st.markdown("Select the folder containing run Excel files to compare a single component across all of them.")

    comp_folder = folder_picker_widget("Runs Folder", "comp_folder_path")

    if "cc_campaign" not in st.session_state:
        st.session_state["cc_campaign"] = None

    if comp_folder:
        if st.button("Load Files", key="cc_load"):
            if os.path.isdir(comp_folder):
                with st.spinner("Loading files..."):
                    st.session_state["cc_campaign"] = load_campaign_from_folder(comp_folder, configs)
                    st.success(f"Loaded {len(st.session_state['cc_campaign'].runs)} runs.")
            else:
                st.error("Invalid folder path.")
    else:
        st.info("Select a folder to begin.")
        st.session_state["cc_campaign"] = None

    if st.session_state["cc_campaign"]:
        campaign = st.session_state["cc_campaign"]
        all_comps_cc = sorted(campaign.list_components())

        comp_name = st.selectbox("Select Component", all_comps_cc, key="cc_comp_sel")

        if comp_name:
            df_cc = compare_component_across_runs(campaign, comp_name)

            st.subheader(f"Comparison: {comp_name}")
            sort_cols = [c for c in df_cc.columns if c != "run_id"]
            sort_by = st.selectbox("Sort by", ["run_id"] + sort_cols, key="cc_sort")
            if sort_by in df_cc.columns:
                df_cc = df_cc.sort_values(sort_by)

            fig_cc = px.line(df_cc, x="run_id", y="max_temp", markers=True,
                             title=f"Max Temp of {comp_name} across runs",
                             hover_data=df_cc.columns)
            cfg_cc = configs.get(comp_name)
            if cfg_cc:
                fig_cc.add_hline(y=cfg_cc.max_limit, line_dash="dash",
                                 line_color="red", annotation_text="Max Limit")
                fig_cc.add_hline(y=cfg_cc.warning_limit, line_dash="dot",
                                 line_color="orange", annotation_text="Warning Limit")
            st.plotly_chart(fig_cc, use_container_width=True)
            st.dataframe(df_cc, use_container_width=True)

            # ── Derating Curve (NEW) ───────────────────────────────────────────
            with st.expander("Thermal Derating Curve", expanded=False):
                x_col_opts = [c for c in df_cc.columns if c not in ("run_id", "max_temp", "steady_state_temp", "steady_reached") and df_cc[c].notna().sum() >= 2]
                if x_col_opts:
                    x_col_sel = st.selectbox("X-axis variable for derating", x_col_opts, key="cc_derate_x")
                    sum_df_cc, curve_df_cc = compute_derating_curve(df_cc, comp_name, x_col=x_col_sel)
                    if "message" not in sum_df_cc.columns:
                        st.dataframe(sum_df_cc, use_container_width=True)
                        fig_der_cc = go.Figure()
                        fig_der_cc.add_trace(
                            go.Scatter(x=df_cc[x_col_sel], y=df_cc["max_temp"],
                                       mode="markers", name="Measured", marker=dict(size=10))
                        )
                        fig_der_cc.add_trace(
                            go.Scatter(x=curve_df_cc[x_col_sel],
                                       y=curve_df_cc["predicted_max_temp"],
                                       mode="lines", name="Linear Fit",
                                       line=dict(dash="dash", color="red"))
                        )
                        if cfg_cc:
                            fig_der_cc.add_hline(y=cfg_cc.max_limit, line_dash="dash",
                                                 line_color="red", annotation_text="Max Limit")
                        fig_der_cc.update_layout(
                            xaxis_title=x_col_sel, yaxis_title="Max Temp (°C)",
                            title=f"Derating Curve — {comp_name}",
                        )
                        st.plotly_chart(fig_der_cc, use_container_width=True)
                    else:
                        st.info(sum_df_cc.iloc[0, 0])
                else:
                    st.info("Need at least one numeric metadata column with ≥ 2 data points.")

            # Downloads & Report
            c1, c2 = st.columns(2)
            c1.download_button("Download Comparison (CSV)", df_cc.to_csv(index=False),
                               file_name=f"compare_{comp_name}.csv", mime="text/csv")

            if c2.button("Generate Report (HTML)", key="cc_gen_rpt"):
                html_cc = generate_section_html_report(
                    f"Component Comparison: {comp_name}",
                    [
                        {
                            "header": f"Temperature Trend: {comp_name}",
                            "content": f"Max temperatures for {comp_name} across {len(df_cc)} runs.",
                            "plotly_fig": fig_cc,
                            "dataframe": df_cc,
                        }
                    ],
                )
                st.session_state["cc_report_html"] = html_cc
                st.session_state["cc_report_name"] = comp_name
                st.success("Report generated.")

            if "cc_report_html" in st.session_state:
                st.download_button(
                    "Download Report (HTML)", st.session_state["cc_report_html"],
                    file_name=f"comp_{st.session_state['cc_report_name']}_report.html",
                    mime="text/html",
                )

# ══════════════════════════════════════════════════════════════════════════════
# MODE: Samples Comparison (A vs B)
# ══════════════════════════════════════════════════════════════════════════════
elif mode == "Samples Comparison (A vs B)":
    st.header("Samples Comparison (A vs B)")
    st.markdown("Select a folder for each sample. Runs are matched by operating conditions.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Sample A — Reference**")
        folder_a = folder_picker_widget("Sample A Folder", "sample_a_folder_path")
    with col2:
        st.markdown("**Sample B — DUT / New Design**")
        folder_b = folder_picker_widget("Sample B Folder", "sample_b_folder_path")

    if st.button("Compare Samples", key="sab_compare"):
        if folder_a and folder_b:
            if not os.path.isdir(folder_a) or not os.path.isdir(folder_b):
                st.error("Both paths must be valid folders.")
            else:
                with st.spinner("Loading and matching samples..."):
                    camp_a = load_campaign_from_folder(folder_a, configs)
                    camp_b = load_campaign_from_folder(folder_b, configs)
                matches = match_runs_by_metadata(camp_a, camp_b)
                st.info(f"Matched {len(matches)} runs based on operating conditions.")

                if matches:
                    rows = []
                    for run_a, run_b in matches:
                        common = set(run_a.available_components()) & set(run_b.available_components())
                        sa = compute_component_stats(run_a)
                        sb = compute_component_stats(run_b)
                        for comp in common:
                            ta = sa[sa["component"] == comp]["max_temp"].values[0]
                            tb = sb[sb["component"] == comp]["max_temp"].values[0]
                            d = tb - ta
                            rec = {
                                "Condition": run_a.run_id,
                                "Component": comp,
                                "Temp A": ta,
                                "Temp B": tb,
                                "Delta (B-A)": d,
                                "Status": "HOTTER" if d > 1.0 else ("COOLER" if d < -1.0 else "SAME"),
                            }
                            rec.update(run_a.metadata)
                            rows.append(rec)

                    comp_df = pd.DataFrame(rows)
                    sig_diff = comp_df[comp_df["Delta (B-A)"].abs() > 5.0].sort_values("Delta (B-A)", ascending=False)

                    st.subheader("Delta Overview (B − A)")
                    fig_sab = px.strip(
                        comp_df, x="Component", y="Delta (B-A)", color="Status",
                        hover_data=["Condition", "Temp A", "Temp B"],
                        title="Temperature Diff: Sample B vs Sample A (positive = B hotter)",
                        color_discrete_map={"HOTTER": "red", "COOLER": "green", "SAME": "gray"},
                    )
                    fig_sab.add_hline(y=0, line_dash="dash", line_color="gray")
                    st.plotly_chart(fig_sab, use_container_width=True)

                    st.subheader("Significant Differences (> 5 °C)")
                    st.dataframe(sig_diff, use_container_width=True)

                    c1, c2 = st.columns(2)
                    c1.download_button("Full Comparison (CSV)", comp_df.to_csv(index=False),
                                       file_name="samples_comparison_full.csv", mime="text/csv")
                    c2.download_button("Significant Differences (CSV)", sig_diff.to_csv(index=False),
                                       file_name="samples_comparison_significant.csv", mime="text/csv")

                    if st.button("Generate Samples Report (HTML)", key="sab_gen_rpt"):
                        html_sab = generate_section_html_report(
                            "Samples Comparison (A vs B)",
                            [
                                {
                                    "header": "Delta Overview",
                                    "content": "Temperature differences between Sample B and Sample A.",
                                    "plotly_fig": fig_sab,
                                },
                                {
                                    "header": "Significant Differences (> 5 °C)",
                                    "content": "Components with major temperature deviations.",
                                    "dataframe": sig_diff if not sig_diff.empty
                                    else pd.DataFrame({"Message": ["No significant differences."]}),
                                },
                                {
                                    "header": "Full Comparison Data",
                                    "dataframe": comp_df,
                                },
                            ],
                        )
                        st.session_state["sab_report_html"] = html_sab
                        st.success("Report generated.")

                    if "sab_report_html" in st.session_state:
                        st.download_button(
                            "Download Report (HTML)", st.session_state["sab_report_html"],
                            file_name="samples_report.html", mime="text/html",
                        )
        else:
            st.error("Please select folders for both Sample A and Sample B.")

# ══════════════════════════════════════════════════════════════════════════════
# MODE: File vs File Comparison
# ══════════════════════════════════════════════════════════════════════════════
elif mode == "File vs File Comparison":
    st.header("File vs File Comparison")
    st.markdown(
        "Upload two thermal test Excel files to compare component temperatures side by side — "
        "useful for evaluating different thermal materials, pads, or design variants."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        file_a = st.file_uploader("File A (Reference / Baseline)", type=["xlsx"], key="fvf_a")
        label_a = st.text_input("Label for File A", value="File A", key="label_a")
    with col_b:
        file_b = st.file_uploader("File B (Test / New Material)", type=["xlsx"], key="fvf_b")
        label_b = st.text_input("Label for File B", value="File B", key="label_b")

    if file_a and file_b:
        try:
            bytes_a, bytes_b = file_a.getvalue(), file_b.getvalue()
            with st.spinner("Loading files..."):
                run_a, stats_a = load_run_and_stats(bytes_a, file_a.name, DEFAULT_TIME_COLUMN)
                run_b, stats_b = load_run_and_stats(bytes_b, file_b.name, DEFAULT_TIME_COLUMN)

            hash_a = hashlib.sha256(bytes_a).hexdigest()
            hash_b = hashlib.sha256(bytes_b).hexdigest()
            limits_a = get_limits_cached(run_a, stats_a, configs, (hash_a, config_path, mtime))
            limits_b = get_limits_cached(run_b, stats_b, configs, (hash_b, config_path, mtime))
            steady_a = get_steady_cached(run_a, window_minutes, slope_threshold,
                                         (hash_a, float(window_minutes), float(slope_threshold)))
            steady_b = get_steady_cached(run_b, window_minutes, slope_threshold,
                                         (hash_b, float(window_minutes), float(slope_threshold)))

            # ── KPIs ──────────────────────────────────────────────────────────
            st.subheader("Summary")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric(f"Max Temp — {label_a}", f"{stats_a['max_temp'].max():.1f} °C")
            k2.metric(f"Max Temp — {label_b}", f"{stats_b['max_temp'].max():.1f} °C",
                      delta=f"{stats_b['max_temp'].max() - stats_a['max_temp'].max():.1f} °C",
                      delta_color="inverse")
            k3.metric(f"Steady State — {label_a}", "Yes" if steady_a["steady"] else "No")
            k4.metric(f"Steady State — {label_b}", "Yes" if steady_b["steady"] else "No")

            fail_a = int((limits_a["status"] == "FAIL").sum())
            fail_b = int((limits_b["status"] == "FAIL").sum())
            warn_a = int((limits_a["status"] == "WARNING").sum())
            warn_b = int((limits_b["status"] == "WARNING").sum())
            k5, k6, k7, k8 = st.columns(4)
            k5.metric(f"Failures — {label_a}", fail_a)
            k6.metric(f"Failures — {label_b}", fail_b, delta=fail_b - fail_a, delta_color="inverse")
            k7.metric(f"Warnings — {label_a}", warn_a)
            k8.metric(f"Warnings — {label_b}", warn_b, delta=warn_b - warn_a, delta_color="inverse")

            # ── Build merged DataFrame ─────────────────────────────────────────
            merged = pd.merge(
                stats_a[["component", "max_temp", "avg_temp", "std_temp"]].rename(
                    columns={"max_temp": f"max_temp_{label_a}", "avg_temp": f"avg_temp_{label_a}",
                             "std_temp": f"std_temp_{label_a}"}),
                stats_b[["component", "max_temp", "avg_temp", "std_temp"]].rename(
                    columns={"max_temp": f"max_temp_{label_b}", "avg_temp": f"avg_temp_{label_b}",
                             "std_temp": f"std_temp_{label_b}"}),
                on="component", how="outer",
            )
            merged["delta_max (B-A)"] = merged[f"max_temp_{label_b}"] - merged[f"max_temp_{label_a}"]
            merged["delta_avg (B-A)"] = merged[f"avg_temp_{label_b}"] - merged[f"avg_temp_{label_a}"]

            def classify(d):
                if pd.isna(d): return "ONLY ONE FILE"
                if d > 2.0:  return "HOTTER"
                if d < -2.0: return "COOLER"
                return "SAME"

            merged["result"] = merged["delta_max (B-A)"].apply(classify)
            merged = pd.merge(merged,
                limits_a[["component", "status", "max_limit", "warning_limit"]].rename(
                    columns={"status": f"status_{label_a}"}),
                on="component", how="left")
            merged = pd.merge(merged,
                limits_b[["component", "status"]].rename(columns={"status": f"status_{label_b}"}),
                on="component", how="left")

            # ── Side-by-side bar chart ─────────────────────────────────────────
            st.subheader("Max Temperature — Side by Side")
            top_n_bar = st.slider("Show top N", 5, len(merged), min(20, len(merged)), key="fvf_topn")
            top_comps = merged.reindex(
                merged[f"max_temp_{label_a}"].fillna(merged[f"max_temp_{label_b}"]).nlargest(top_n_bar).index
            )
            fig_fvf_bar = go.Figure()
            fig_fvf_bar.add_trace(go.Bar(name=label_a, x=top_comps["component"],
                                         y=top_comps[f"max_temp_{label_a}"], marker_color="steelblue"))
            fig_fvf_bar.add_trace(go.Bar(name=label_b, x=top_comps["component"],
                                         y=top_comps[f"max_temp_{label_b}"], marker_color="tomato"))
            fig_fvf_bar.update_layout(barmode="group", xaxis_tickangle=-45,
                                      yaxis_title="Max Temperature (°C)", hovermode="x unified")
            st.plotly_chart(fig_fvf_bar, use_container_width=True)

            # ── Delta chart ────────────────────────────────────────────────────
            st.subheader(f"Temperature Delta: {label_b} − {label_a}")
            delta_sorted = merged.dropna(subset=["delta_max (B-A)"]).sort_values("delta_max (B-A)", ascending=False)
            color_map_delta = {"HOTTER": "red", "COOLER": "green", "SAME": "gray"}
            fig_delta = go.Figure(go.Bar(
                x=delta_sorted["component"], y=delta_sorted["delta_max (B-A)"],
                marker_color=delta_sorted["result"].map(color_map_delta),
                text=delta_sorted["delta_max (B-A)"].apply(lambda x: f"{x:+.1f}°C"),
                textposition="outside",
            ))
            fig_delta.add_hline(y=0, line_dash="dash", line_color="black")
            fig_delta.update_layout(xaxis_tickangle=-45, yaxis_title="ΔT (°C)",
                                    title="Positive = B is hotter, Negative = B is cooler")
            st.plotly_chart(fig_delta, use_container_width=True)

            # ── Time series overlay ────────────────────────────────────────────
            st.subheader("Time Series Overlay")
            common_comps = sorted(set(run_a.available_components()) & set(run_b.available_components()))
            if common_comps:
                sel_comp = st.selectbox("Select component to overlay", common_comps, key="fvf_ts_comp")
                fig_fvf_ts = go.Figure()
                x_a = run_a.timestamps if run_a.timestamps is not None and not run_a.timestamps.isna().all() else run_a.time / 60.0
                x_b = run_b.timestamps if run_b.timestamps is not None and not run_b.timestamps.isna().all() else run_b.time / 60.0
                fig_fvf_ts.add_trace(go.Scatter(x=x_a, y=run_a.data[sel_comp], mode="lines",
                                                name=label_a, line=dict(color="steelblue")))
                fig_fvf_ts.add_trace(go.Scatter(x=x_b, y=run_b.data[sel_comp], mode="lines",
                                                name=label_b, line=dict(color="tomato")))
                cfg_fvf = configs.get(sel_comp)
                if cfg_fvf:
                    fig_fvf_ts.add_hline(y=cfg_fvf.max_limit, line_dash="dash", line_color="red",
                                         annotation_text="Max Limit")
                    fig_fvf_ts.add_hline(y=cfg_fvf.warning_limit, line_dash="dot", line_color="orange",
                                         annotation_text="Warning")
                fig_fvf_ts.update_layout(yaxis_title="Temperature (°C)", hovermode="x unified",
                                         title=f"Temperature Profile: {sel_comp}")
                st.plotly_chart(fig_fvf_ts, use_container_width=True)

            # ── Limit status changes ───────────────────────────────────────────
            st.subheader("Limit Status Changes")
            status_changed = merged[
                merged[f"status_{label_a}"] != merged[f"status_{label_b}"]
            ].dropna(subset=[f"status_{label_a}", f"status_{label_b}"])
            if not status_changed.empty:
                st.warning(f"{len(status_changed)} component(s) changed pass/fail status.")
                st.dataframe(
                    status_changed[["component", f"status_{label_a}", f"status_{label_b}",
                                    f"max_temp_{label_a}", f"max_temp_{label_b}", "delta_max (B-A)"]],
                    use_container_width=True,
                )
            else:
                st.success("No components changed pass/fail status.")

            # ── Full comparison table ──────────────────────────────────────────
            st.subheader("Full Component Comparison Table")
            filter_res = st.multiselect(
                "Filter by result", ["HOTTER", "COOLER", "SAME", "ONLY ONE FILE"],
                default=["HOTTER", "COOLER", "SAME", "ONLY ONE FILE"], key="fvf_filter",
            )
            display_df = merged[merged["result"].isin(filter_res)].copy()

            def style_result(val):
                cm = {"HOTTER": "color:red;font-weight:bold",
                      "COOLER": "color:green;font-weight:bold",
                      "SAME": "color:gray", "ONLY ONE FILE": "color:orange"}
                return cm.get(val, "")

            float_cols = [c for c in display_df.columns if display_df[c].dtype == float]
            st.dataframe(
                display_df.style.map(style_result, subset=["result"])
                .format({c: "{:.2f}" for c in float_cols}, na_rep="—"),
                use_container_width=True,
            )

            # ── Downloads (CSV + Excel) (NEW Excel export) ─────────────────────
            st.subheader("Downloads")
            dl1, dl2, dl3, dl4 = st.columns(4)
            dl1.download_button("Full Comparison (CSV)", merged.to_csv(index=False),
                                file_name="file_vs_file_comparison.csv", mime="text/csv")
            dl2.download_button(f"Stats {label_a} (CSV)", stats_a.to_csv(index=False),
                                file_name=f"stats_{label_a}.csv", mime="text/csv")
            dl3.download_button(f"Stats {label_b} (CSV)", stats_b.to_csv(index=False),
                                file_name=f"stats_{label_b}.csv", mime="text/csv")

            # Excel export with multiple sheets
            if dl4.button("Export Excel (Multi-Sheet)", key="fvf_excel_btn"):
                xl_buf = io.BytesIO()
                with pd.ExcelWriter(xl_buf, engine="xlsxwriter") as writer:
                    merged.to_excel(writer, sheet_name="Comparison", index=False)
                    stats_a.to_excel(writer, sheet_name=f"Stats_{label_a}"[:31], index=False)
                    stats_b.to_excel(writer, sheet_name=f"Stats_{label_b}"[:31], index=False)
                    limits_a.to_excel(writer, sheet_name=f"Limits_{label_a}"[:31], index=False)
                    limits_b.to_excel(writer, sheet_name=f"Limits_{label_b}"[:31], index=False)
                    for ws in writer.sheets.values():
                        ws.autofit()
                xl_buf.seek(0)
                st.session_state["fvf_excel"] = xl_buf.getvalue()

            if "fvf_excel" in st.session_state:
                st.download_button(
                    "Download Excel Report", st.session_state["fvf_excel"],
                    file_name="file_vs_file_comparison.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        except Exception as e:
            st.error(f"Error during comparison: {e}")
    else:
        st.info("Upload both File A and File B to begin comparison.")

# ══════════════════════════════════════════════════════════════════════════════
# MODE: Configuration Editor
# ══════════════════════════════════════════════════════════════════════════════
elif mode == "Configuration Editor":
    st.header("Configuration Editor")
    st.markdown("Edit component limits and groups directly. Changes are saved to `config/components.csv`.")
    st.caption(f"Editing file: {config_path}")

    config_ext = os.path.splitext(config_path)[1].lower()

    try:
        if config_ext == ".json":
            with open(config_path, "r", encoding="utf-8") as f:
                raw_records = json.load(f)
            raw_df = pd.DataFrame(raw_records)
        else:
            raw_df = pd.read_csv(config_path)
    except Exception as e:
        st.error(f"Failed to load config file: {e}")
        raw_df = pd.DataFrame(
            columns=["name_raw", "display_name", "group", "max_limit",
                     "warning_limit", "critical_limit", "color_hint"]
        )

    edited_df = st.data_editor(raw_df, num_rows="dynamic", use_container_width=True)

    if st.button("Save Configuration", type="primary"):
        try:
            out_dir = os.path.dirname(os.path.abspath(config_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            if config_ext == ".json":
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(edited_df.to_dict(orient="records"), f, indent=2)
            else:
                edited_df.to_csv(config_path, index=False)
            get_configs.clear()
            st.session_state.pop("limits_cache", None)
            st.success(f"Configuration saved to {config_path} and reloaded!")
            st.balloons()
        except Exception as e:
            st.error(f"Failed to save configuration: {e}")

    st.divider()

    # ── Global Defaults Editor ────────────────────────────────────────────────
    st.subheader("Global Defaults")
    st.markdown(
        "These are the fallback values used for components **not listed** in `components.csv`, "
        "and the time-column name expected in your Excel files. "
        "Changes take effect immediately after saving (the app reloads automatically)."
    )

    _config_py = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.py")
    )

    try:
        _current = _read_global_defaults(_config_py)
    except Exception as e:
        st.error(f"Could not read config.py: {e}")
        _current = {}

    if _current:
        with st.form("global_defaults_form"):
            _new_vals = {}
            for key, spec in _GLOBAL_DEFAULTS_SPEC.items():
                cur = _current.get(key, "")
                if spec["type"] == "str":
                    _new_vals[key] = st.text_input(spec["label"], value=str(cur),
                                                    help=spec["help"], key=f"gd_{key}")
                else:
                    _new_vals[key] = st.number_input(spec["label"], value=float(cur),
                                                      step=1.0, format="%.1f",
                                                      help=spec["help"], key=f"gd_{key}")
            submitted = st.form_submit_button("Save Global Defaults", type="primary")

        if submitted:
            try:
                _write_global_defaults(_config_py, _new_vals)
                for _k in list(sys.modules.keys()):
                    if _k.startswith("thermal_analyzer"):
                        del sys.modules[_k]
                get_configs.clear()
                load_run_and_stats.clear()
                st.session_state.pop("limits_cache", None)
                st.session_state.pop("steady_cache", None)
                st.success("Global defaults saved. Reloading dashboard...")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save global defaults: {e}")
