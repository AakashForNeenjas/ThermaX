"""
Phase-separation analysis: splits a run into a startup (transient) phase and
a main (steady-operating) phase so you can compare peak vs. operating temperatures.
"""
import pandas as pd
import numpy as np
from ..models import ThermalRun


def split_phases(run: ThermalRun, startup_minutes: float = 5.0) -> dict:
    """
    Split a ThermalRun into two phases based on elapsed time.

    Parameters
    ----------
    run              : ThermalRun to analyse
    startup_minutes  : Duration (minutes) to treat as the startup / transient phase.

    Returns
    -------
    dict with keys:
        startup_data, main_data     – DataFrames of component temperatures
        startup_time, main_time     – corresponding time Series (seconds)
        startup_duration_s          – cutoff in seconds
    """
    cutoff_s = startup_minutes * 60.0
    mask_start = run.time <= cutoff_s
    mask_main = run.time > cutoff_s

    return {
        "startup_data": run.data[mask_start.values].reset_index(drop=True),
        "main_data": run.data[mask_main.values].reset_index(drop=True),
        "startup_time": run.time[mask_start.values].reset_index(drop=True),
        "main_time": run.time[mask_main.values].reset_index(drop=True),
        "startup_duration_s": cutoff_s,
    }


def compute_phase_stats(run: ThermalRun, startup_minutes: float = 5.0) -> pd.DataFrame:
    """
    Compute per-component temperature statistics for each phase separately.

    Returns DataFrame with columns:
        component, startup_max (°C), main_max (°C), transient_spike (°C)

    A positive transient_spike means the component ran hotter during startup.
    Sorted descending by transient_spike so the worst offenders appear first.
    """
    phases = split_phases(run, startup_minutes)
    results = []

    for comp in run.available_components():
        s_data = phases["startup_data"]
        m_data = phases["main_data"]

        startup_max = float(s_data[comp].max()) if comp in s_data.columns and not s_data.empty else np.nan
        main_max = float(m_data[comp].max()) if comp in m_data.columns and not m_data.empty else np.nan

        spike = (startup_max - main_max) if not (np.isnan(startup_max) or np.isnan(main_max)) else np.nan

        results.append(
            {
                "component": comp,
                "startup_max (°C)": startup_max,
                "main_max (°C)": main_max,
                "transient_spike (°C)": spike,
            }
        )

    df = pd.DataFrame(results)
    return df.sort_values("transient_spike (°C)", ascending=False, na_position="last")
