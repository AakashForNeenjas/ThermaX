"""
Campaign-level anomaly and fault detection.
"""
import pandas as pd
import numpy as np
from typing import List

from ..models import ThermalRun, TestCampaign
from .stats import compute_component_stats


def detect_anomalies(
    campaign: TestCampaign,
    z_threshold: float = 2.5,
) -> pd.DataFrame:
    """
    Flag runs where a component's max_temp is unusually high or low compared
    to the campaign-wide mean for that component (z-score method).

    Parameters
    ----------
    campaign     : TestCampaign to scan
    z_threshold  : Absolute z-score above which a reading is flagged.

    Returns
    -------
    DataFrame of anomalous readings with columns:
        run_id, component, max_temp, campaign_mean, campaign_std,
        z_score, anomaly_type  ('UNUSUALLY HOT' | 'UNUSUALLY COLD')
    Sorted by |z_score| descending.  Empty DataFrame if none found.
    """
    records = []
    for run in campaign.runs:
        stats = compute_component_stats(run)
        for _, row in stats.iterrows():
            records.append(
                {
                    "run_id": run.run_id,
                    "component": row["component"],
                    "max_temp": row["max_temp"],
                }
            )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    df["campaign_mean"] = df.groupby("component")["max_temp"].transform("mean")
    df["campaign_std"] = df.groupby("component")["max_temp"].transform("std")

    # Avoid division by zero for constant-temperature components
    std_safe = df["campaign_std"].replace(0, np.nan)
    df["z_score"] = (df["max_temp"] - df["campaign_mean"]) / std_safe

    df["anomaly_type"] = "Normal"
    df.loc[df["z_score"] > z_threshold, "anomaly_type"] = "UNUSUALLY HOT"
    df.loc[df["z_score"] < -z_threshold, "anomaly_type"] = "UNUSUALLY COLD"

    anomalies = df[df["anomaly_type"] != "Normal"].copy()
    anomalies["abs_z"] = anomalies["z_score"].abs()
    anomalies = anomalies.sort_values("abs_z", ascending=False).drop(columns="abs_z")
    return anomalies.reset_index(drop=True)


def detect_flat_sensors(
    run: ThermalRun,
    min_std_threshold: float = 0.1,
) -> List[str]:
    """
    Identify components whose temperature barely changes — likely disconnected
    or malfunctioning sensors.

    Returns a list of suspect component column names.
    """
    return [
        comp
        for comp in run.available_components()
        if run.data[comp].std() < min_std_threshold
    ]
