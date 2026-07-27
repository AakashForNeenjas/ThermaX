import pandas as pd
from datetime import datetime, timedelta

def parse_time_string(time_str: str) -> float:
    """
    Parse a time string (e.g., 'HH:MM:SS') into seconds from midnight 
    or just return seconds if it's already numeric.
    """
    if isinstance(time_str, (int, float)):
        return float(time_str)
    
    try:
        # Try parsing HH:MM:SS
        t = datetime.strptime(str(time_str), "%H:%M:%S")
        return t.hour * 3600 + t.minute * 60 + t.second
    except ValueError:
        pass
        
    try:
        # Try parsing HH:MM:SS.f
        t = datetime.strptime(str(time_str), "%H:%M:%S.%f")
        return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6
    except ValueError:
        pass

    # Fallback: try pandas to_timedelta
    try:
        td = pd.to_timedelta(time_str)
        return td.total_seconds()
    except Exception:
        return float("nan")

def seconds_to_hms(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    return str(timedelta(seconds=int(seconds)))
