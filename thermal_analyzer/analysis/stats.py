import pandas as pd
import numpy as np
from ..models import ThermalRun

def compute_component_stats(run: ThermalRun, threshold_temp: float = 80.0) -> pd.DataFrame:
    """
    Compute statistics for each component in the run.
    """
    stats_list = []
    
    # Time delta for dT/dt calculation (assuming roughly constant step or taking mean step)
    # We can use gradient.
    # time is in seconds.
    time_values = run.time.values
    
    for col in run.data.columns:
        series = run.data[col]
        
        # Basic stats
        max_temp = series.max()
        min_temp = series.min()
        avg_temp = series.mean()
        median_temp = series.median()
        std_temp = series.std()
        
        # Dynamic metrics
        # Calculate derivative dT/dt
        # We can use numpy gradient
        if len(time_values) > 1:
            # gradient returns dY/dX roughly
            # We need to handle non-uniform time potentially, but np.gradient supports it
            dT = np.gradient(series.values, time_values)
            max_dTdt = np.nanmax(dT)
        else:
            max_dTdt = 0.0
            
        # Time of max
        if not pd.isna(max_temp):
            idx_max = series.idxmax()
            # idx_max is the index label, but run.time is a Series with same index
            # Assuming default integer index for now if read from Excel
            # If index is not aligned, we need to be careful.
            # In excel_loader, we didn't set index on data. So it's RangeIndex.
            time_of_max = run.time.iloc[idx_max]
        else:
            time_of_max = np.nan
            
        # Time to threshold temperature
        threshold_col = f"time_to_{int(threshold_temp)}C"
        over_thresh = series[series >= threshold_temp]
        if not over_thresh.empty:
            first_idx = over_thresh.index[0]
            time_to_threshold = run.time.iloc[first_idx]
        else:
            time_to_threshold = np.nan

        stats_list.append({
            "component": col,
            "max_temp": max_temp,
            "min_temp": min_temp,
            "avg_temp": avg_temp,
            "median_temp": median_temp,
            "std_temp": std_temp,
            "max_dTdt": max_dTdt,
            "time_of_max": time_of_max,
            threshold_col: time_to_threshold
        })
        
    return pd.DataFrame(stats_list)
