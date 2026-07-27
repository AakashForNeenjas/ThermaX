import pandas as pd
import numpy as np
from ..models import ThermalRun

def compute_temp_rise(run: ThermalRun, ambient_temp: float) -> pd.DataFrame:
    """
    Compute temperature rise (Delta T) for each component above ambient.
    Returns DataFrame with [component, t_max, delta_t]
    """
    results = []
    for col in run.data.columns:
        series = run.data[col]
        max_temp = series.max()
        delta_t = max_temp - ambient_temp
        results.append({
            "component": col,
            "max_temp": max_temp,
            "delta_t": delta_t
        })
    
    return pd.DataFrame(results).sort_values("delta_t", ascending=False)

def compute_thermal_resistance(run: ThermalRun, power_w: float, ambient_temp: float) -> pd.DataFrame:
    """
    Compute thermal resistance R_th = Delta T / Power.
    R_th is in °C/W.
    Note: Ideally Power should be per-component power loss. 
    If 'power_w' is total system loss, this calculates 'Effective R_th' relative to total loss.
    """
    df = compute_temp_rise(run, ambient_temp)
    
    if power_w > 0:
        df["R_th (°C/W)"] = df["delta_t"] / power_w
    else:
        df["R_th (°C/W)"] = np.nan
        
    return df

def compute_time_constants(run: ThermalRun) -> pd.DataFrame:
    """
    Estimate thermal time constant (tau) for each component.
    Method: Find time to reach 63.2% of the total temperature rise.
    T(tau) = T_start + 0.632 * (T_final - T_start)
    """
    results = []
    
    # Ensure we use seconds for calculation
    if run.time.empty:
        return pd.DataFrame()
        
    t_seconds = run.time.values
    t_start = t_seconds[0]
    
    for col in run.data.columns:
        series = run.data[col].values
        
        # We assume heating curve
        T_start = series[0]
        T_max = np.nanmax(series)
        
        # Check if there is a significant rise
        if (T_max - T_start) < 2.0:
            tau = np.nan
        else:
            # Target temperature for 1 tau
            T_target = T_start + 0.632 * (T_max - T_start)
            
            # Find first time where Temp >= T_target
            # We use argmax on the boolean array to find first True index
            mask = series >= T_target
            if mask.any():
                idx = np.argmax(mask)
                t_target = t_seconds[idx]
                tau = t_target - t_start
            else:
                tau = np.nan
        
        results.append({
            "component": col,
            "tau (s)": tau,
            "tau (min)": tau / 60.0 if not np.isnan(tau) else np.nan
        })
        
    return pd.DataFrame(results).sort_values("tau (s)", ascending=True)
