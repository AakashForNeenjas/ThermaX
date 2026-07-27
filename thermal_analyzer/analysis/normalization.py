"""
Ambient-temperature normalization and thermal derating-curve utilities.
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple


def normalize_to_ambient(
    stats_df: pd.DataFrame,
    measured_ambient: float,
    reference_ambient: float = 25.0,
) -> pd.DataFrame:
    """
    Shift all temperature columns so the result looks as if the test were run
    at *reference_ambient* instead of *measured_ambient*.

    The correction is a simple linear offset:
        T_norm = T_measured - (T_ambient_measured - T_ambient_ref)

    Adds columns: max_temp_norm, avg_temp_norm, min_temp_norm,
                  reference_ambient, measured_ambient, offset_applied.
    Original columns are unchanged.
    """
    df = stats_df.copy()
    offset = measured_ambient - reference_ambient

    for col in ("max_temp", "avg_temp", "min_temp"):
        if col in df.columns:
            df[f"{col}_norm"] = df[col] - offset

    df["reference_ambient"] = reference_ambient
    df["measured_ambient"] = measured_ambient
    df["offset_applied"] = -offset
    return df


def compute_derating_curve(
    comparison_df: pd.DataFrame,
    component: str,
    x_col: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fit a linear derating curve (max_temp vs an independent variable) for one
    component across multiple runs.

    Parameters
    ----------
    comparison_df : output of compare_component_across_runs()
    component     : component name (for labelling)
    x_col         : independent variable column.  Defaults to 'ambient_temp'
                    if present, otherwise raises ValueError.

    Returns
    -------
    summary_df : DataFrame with slope, intercept, r², x_variable
    curve_df   : DataFrame with x values and predicted_max_temp (for plotting)
    """
    if comparison_df.empty:
        empty = pd.DataFrame()
        return empty, empty

    # Resolve x_col
    if x_col is None:
        if "ambient_temp" in comparison_df.columns:
            x_col = "ambient_temp"
        else:
            raise ValueError(
                "No x_col specified and 'ambient_temp' not found in comparison_df. "
                "Pass x_col explicitly."
            )

    valid = comparison_df[["max_temp", x_col]].dropna()
    if len(valid) < 2:
        empty = pd.DataFrame({"message": ["Not enough data points (need ≥ 2)."]})
        return empty, empty

    x = valid[x_col].values.astype(float)
    y = valid["max_temp"].values.astype(float)

    slope, intercept = np.polyfit(x, y, 1)
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2) if len(x) > 1 else float("nan")

    summary_df = pd.DataFrame(
        {
            "component": [component],
            "x_variable": [x_col],
            f"slope (°C per {x_col} unit)": [round(slope, 4)],
            "intercept": [round(intercept, 2)],
            "r²": [round(r2, 4)],
        }
    )

    # Generate smooth fitted line for plotting
    x_range = np.linspace(x.min(), x.max(), 80)
    curve_df = pd.DataFrame(
        {x_col: x_range, "predicted_max_temp": slope * x_range + intercept}
    )

    return summary_df, curve_df
