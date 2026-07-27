import pandas as pd
from typing import Dict, Any
from ..models import ThermalRun

def export_run_summary_to_excel(
    run: ThermalRun,
    component_stats: pd.DataFrame,
    limit_eval: pd.DataFrame,
    steady_state_info: Dict[str, Any],
    output_path: str
):
    """
    Export analysis results to a multi-sheet Excel file.
    """
    with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
        # 1. Summary Sheet
        summary_data = {
            "Run ID": [run.run_id],
            "File Path": [run.file_path],
            "Notes": [run.notes or ""],
            "Steady State Reached": [steady_state_info.get("steady", False)],
            "Steady State Reason": [steady_state_info.get("reason", "")],
            "Time to Steady State": [steady_state_info.get("t_steady_state", "N/A")]
        }
        # Add metadata
        for k, v in run.metadata.items():
            summary_data[k] = [v]
            
        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)
        
        # 2. Component Stats
        component_stats.to_excel(writer, sheet_name="Component_Stats", index=False)
        
        # 3. Limit Checks
        limit_eval.to_excel(writer, sheet_name="Limit_Checks", index=False)
        
        # 4. Steady State Details
        # Create a DF from the slopes dict
        slopes = steady_state_info.get("slopes_per_min", {})
        ss_temps = steady_state_info.get("component_steady_temps", {})
        
        ss_data = []
        for comp, slope in slopes.items():
            ss_data.append({
                "Component": comp,
                "Slope (degC/min)": slope,
                "Steady Temp": ss_temps.get(comp, None)
            })
        pd.DataFrame(ss_data).to_excel(writer, sheet_name="Steady_State_Details", index=False)
        
        # Formatting (optional, basic auto-width)
        for sheet in writer.sheets.values():
            sheet.autofit()
