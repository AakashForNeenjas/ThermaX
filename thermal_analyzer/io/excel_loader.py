import io
import pandas as pd
import os
import logging
from typing import Dict
from ..models import ThermalRun, ComponentConfig
from ..config import DEFAULT_TIME_COLUMN
from ..utils.time_utils import parse_time_string

logger = logging.getLogger(__name__)

def _build_thermal_run_from_df(
    df: pd.DataFrame,
    run_id: str,
    file_path: str,
    time_column: str
) -> ThermalRun:
    # Check time column
    if time_column not in df.columns:
        raise ValueError(f"Time column '{time_column}' not found in {file_path}")

    # Process Time
    # Convert to seconds from start
    raw_time_values = df[time_column]
    raw_time = raw_time_values.apply(parse_time_string)

    # Calculate elapsed time relative to the first valid timestamp
    start_time = raw_time.iloc[0]
    elapsed_time = raw_time - start_time

    # Create timestamps for plotting (try to get datetime objects)
    try:
        # Check if it's already datetime
        if pd.api.types.is_datetime64_any_dtype(raw_time_values):
            timestamps = raw_time_values
        else:
            # Try flexible parsing
            # If it's just time strings, this will attach today's date, which is fine for axis formatting
            timestamps = pd.to_datetime(raw_time_values, errors='coerce')

            # If we have many NaT, it might be because of format mismatch or it's just float seconds?
            # If it's float seconds, we can't easily make it "Real Time" without a start reference.
            # But the user said "Values are timestamps like HH:MM:SS".
    except Exception:
        timestamps = pd.Series([None] * len(df))

    # Process Data Columns
    # Filter only columns that are not the time column
    data_cols = [c for c in df.columns if c != time_column]

    # Coerce to numeric
    clean_data = df[data_cols].apply(pd.to_numeric, errors='coerce')

    return ThermalRun(
        run_id=run_id,
        file_path=file_path,
        time=elapsed_time,
        timestamps=timestamps,
        data=clean_data
    )


def load_thermal_run(
    file_path: str,
    component_configs: Dict[str, ComponentConfig],
    time_column: str = DEFAULT_TIME_COLUMN
) -> ThermalRun:
    """
    Load a single thermal test run from an Excel file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Loading thermal run from {file_path}")

    # Load Excel
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file {file_path}: {e}")

    run_id = os.path.splitext(os.path.basename(file_path))[0]
    return _build_thermal_run_from_df(df, run_id, file_path, time_column)


def load_thermal_run_from_bytes(
    file_bytes: bytes,
    file_name: str,
    component_configs: Dict[str, ComponentConfig],
    time_column: str = DEFAULT_TIME_COLUMN
) -> ThermalRun:
    """
    Load a single thermal test run from raw Excel file bytes.
    """
    if not file_bytes:
        raise ValueError("No data provided for Excel file bytes.")

    logger.info(f"Loading thermal run from uploaded bytes ({file_name})")

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f"Failed to read Excel bytes for {file_name}: {e}")

    run_id = os.path.splitext(os.path.basename(file_name))[0]
    return _build_thermal_run_from_df(df, run_id, file_name, time_column)
