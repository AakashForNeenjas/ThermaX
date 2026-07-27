import pandas as pd
from typing import Dict, List
from ..models import TestCampaign, ComponentConfig
from ..config import DEFAULT_MAX_LIMIT
from .stats import compute_component_stats
from .steady_state import detect_steady_state

def compare_component_across_runs(
    campaign: TestCampaign,
    component_name: str
) -> pd.DataFrame:
    """
    Compare a single component across all runs in the campaign.
    """
    records = []
    
    for run in campaign.runs:
        if component_name not in run.available_components():
            continue
            
        # Get max temp
        series = run.data[component_name]
        max_temp = series.max()
        
        # Get steady state (optional, expensive if we re-run it every time)
        # Ideally steady state should be cached or pre-computed.
        # For now, we compute it quickly.
        ss_res = detect_steady_state(run, critical_components=[component_name])
        ss_temp = series.iloc[-1] if ss_res['steady'] else None
        
        rec = {
            "run_id": run.run_id,
            "max_temp": max_temp,
            "steady_state_temp": ss_temp,
            "steady_reached": ss_res['steady']
        }
        # Add metadata
        rec.update(run.metadata)
        
        records.append(rec)
        
    return pd.DataFrame(records)

def get_worst_case_components(
    campaign: TestCampaign,
    component_configs: Dict[str, ComponentConfig],
    top_n: int = 10
) -> pd.DataFrame:
    """
    Find the worst-case (hottest) component-run combinations.
    """
    all_records = []
    
    for run in campaign.runs:
        stats = compute_component_stats(run)
        for _, row in stats.iterrows():
            comp = row['component']
            max_t = row['max_temp']
            
            # Margin calculation
            config = component_configs.get(comp)
            limit = config.max_limit if config else DEFAULT_MAX_LIMIT
            margin = limit - max_t
            
            all_records.append({
                "run_id": run.run_id,
                "component": comp,
                "max_temp": max_t,
                "limit": limit,
                "margin": margin,
                "metadata": str(run.metadata)
            })
            
    df = pd.DataFrame(all_records)
    if df.empty:
        return df
        
    # Sort by max_temp descending (or margin ascending)
    # Let's sort by max_temp for "hottest"
    df_sorted = df.sort_values(by="max_temp", ascending=False)
    
    return df_sorted.head(top_n)
