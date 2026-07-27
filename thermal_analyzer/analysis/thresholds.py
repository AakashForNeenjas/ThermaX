import pandas as pd
import numpy as np
from typing import Dict
from ..models import ThermalRun, ComponentConfig
from ..config import DEFAULT_MAX_LIMIT, DEFAULT_WARNING_LIMIT
from .stats import compute_component_stats

def evaluate_limits(
    run: ThermalRun,
    component_configs: Dict[str, ComponentConfig],
    stats: pd.DataFrame | None = None
) -> pd.DataFrame:
    """
    Check components against their configured limits.
    """
    # Get basic stats first to get max_temp
    if stats is None:
        stats = compute_component_stats(run)
    
    results = []
    
    for _, row in stats.iterrows():
        comp_name = row['component']
        max_temp = row['max_temp']
        
        # Get config or default
        config = component_configs.get(comp_name)
        
        # Defaults if not found
        if config:
            warning_limit = config.warning_limit
            max_limit = config.max_limit
        else:
            # Fallback to global defaults
            warning_limit = DEFAULT_WARNING_LIMIT
            max_limit = DEFAULT_MAX_LIMIT
            
        margin_to_warning = warning_limit - max_temp
        margin_to_max = max_limit - max_temp
        
        # Calculate time above limits
        series = run.data[comp_name]
        # Calculate accurate time above threshold (seconds) by integrating intervals
        def compute_time_above(y: pd.Series, t: pd.Series, threshold: float) -> float:
                """Compute the total time (seconds) where y >= threshold.

                This treats the signal as piecewise-linear between samples and integrates
                per-interval. It is robust to non-uniform sampling.
                """
                y_vals = y.to_numpy()
                t_vals = t.to_numpy()

                if len(t_vals) < 2:
                    return 0.0

                total = 0.0

                for i in range(len(t_vals) - 1):
                    t0, t1 = float(t_vals[i]), float(t_vals[i + 1])
                    y0, y1 = float(y_vals[i]) if not pd.isna(y_vals[i]) else np.nan, float(y_vals[i + 1]) if not pd.isna(y_vals[i + 1]) else np.nan

                    # Skip intervals with NaNs
                    if np.isnan(y0) or np.isnan(y1) or t1 <= t0:
                        continue

                    dt = t1 - t0

                    # Fully above or fully below
                    if (y0 >= threshold) and (y1 >= threshold):
                        total += dt
                    elif (y0 < threshold) and (y1 < threshold):
                        continue
                    else:
                        # Crossing case: linear interpolation to find crossing time
                        # fraction at which signal hits threshold between y0 and y1
                        if y1 == y0:
                            # Shouldn't happen (covered above) but guard anyway
                            continue
                        frac = (threshold - y0) / (y1 - y0)
                        # Clamp just in case
                        frac = max(0.0, min(1.0, frac))
                        t_cross = t0 + frac * dt

                        if y0 < threshold and y1 >= threshold:
                            # rising through threshold -> time above in interval is t1 - t_cross
                            total += (t1 - t_cross)
                        elif y0 >= threshold and y1 < threshold:
                            # falling through threshold -> time above is t_cross - t0
                            total += (t_cross - t0)

                return total

        time_above_warning = compute_time_above(series, run.time, warning_limit)
        time_above_max = compute_time_above(series, run.time, max_limit)
        
        # Status
        if max_temp >= max_limit:
            status = "FAIL"
        elif max_temp >= warning_limit:
            status = "WARNING"
        else:
            status = "OK"
            
        results.append({
            "component": comp_name,
            "max_temp": max_temp,
            "warning_limit": warning_limit,
            "max_limit": max_limit,
            "margin_to_warning": margin_to_warning,
            "margin_to_max": margin_to_max,
            "time_above_warning": time_above_warning,
            "time_above_max": time_above_max,
            "status": status
        })
        
    return pd.DataFrame(results)
