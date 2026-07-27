import numpy as np
from typing import Dict, Any, List
from ..models import ThermalRun

def detect_steady_state(
    run: ThermalRun,
    window_minutes: float = 10.0,
    slope_threshold: float = 1,
    critical_components: List[str] = None
) -> Dict[str, Any]:
    """
    Detect if and when the system reached steady state.
    Steady state is defined as slope < threshold for a window of time.
    """
    # Convert window to seconds
    window_seconds = window_minutes * 60.0
    
    # If no critical components specified, use all
    if not critical_components:
        cols = run.data.columns.tolist()
    else:
        cols = [c for c in critical_components if c in run.data.columns]
        
    if not cols:
        return {"t_steady_state": None, "steady": False}

    # We need to slide a window.
    # Since data might not be uniformly sampled in time, we should use time-based windowing.
    # However, for simplicity and performance, if we assume roughly constant sampling, 
    # we can estimate number of samples.
    
    # Let's try a more robust approach: check the last window_seconds of the run first.
    # If that is steady, we work backwards to find where it started?
    # Or just check if the END is steady. 
    # The requirement says "Detect steady-state conditions".
    # Usually we want to know: "Did it reach steady state? If so, what are the final temps?"
    
    # Let's check the slope of the last 'window_minutes' of data.
    
    t_end = run.time.iloc[-1]
    t_start_window = t_end - window_seconds
    
    if t_start_window < run.time.iloc[0]:
        # Run is shorter than window
        return {"t_steady_state": None, "steady": False, "reason": "Run too short"}
        
    # Get indices for the window
    mask = run.time >= t_start_window
    window_data = run.data.loc[mask, cols]
    window_time = run.time.loc[mask]
    
    # Calculate slope for each component in this window
    # Linear regression: T = a*t + b. We want 'a'.
    # np.polyfit(x, y, 1) returns [slope, intercept]
    
    is_steady = True
    slopes = {}
    unstable_details = []
    
    for col in cols:
        y = window_data[col].values
        x = window_time.values
        
        # simple linear regression
        if len(x) > 1:
            slope, _ = np.polyfit(x, y, 1)
            # slope is degC / second.
            # Convert to degC / minute
            slope_per_min = slope * 60.0
        else:
            slope_per_min = 999.0
            
        slopes[col] = slope_per_min
        
        if abs(slope_per_min) > slope_threshold:
            is_steady = False
            unstable_details.append(f"{col} ({slope_per_min:.3f} °C/min)")
            
    # If steady, we can say steady state was reached at t_start_window (conservative)
    # or just say the run IS in steady state at the end.
    
    if is_steady:
        reason = "Steady state achieved."
    else:
        # Sort unstable details to show worst offenders first?
        # For now just list them.
        reason = f"Unstable components (> {slope_threshold} °C/min): " + ", ".join(unstable_details)
    
    result = {
        "steady": is_steady,
        "t_steady_state": t_start_window if is_steady else None,
        "slopes_per_min": slopes,
        "component_steady_temps": run.data.iloc[-1].to_dict() if is_steady else {},
        "reason": reason,
        "unstable_components": unstable_details
    }
    
    return result
