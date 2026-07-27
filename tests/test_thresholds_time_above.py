import pandas as pd
import math
import tempfile
import os

from thermal_analyzer.io.excel_loader import load_thermal_run
from thermal_analyzer.analysis.thresholds import evaluate_limits
from thermal_analyzer.models import ComponentConfig


def create_sample_xlsx(path: str):
    # times every 10 seconds
    df = pd.DataFrame({
        'MCGS_TIME': ['00:00:00', '00:00:10', '00:00:20', '00:00:30'],
        'C1': [50, 90, 90, 50]
    })
    df.to_excel(path, index=False)


def test_time_above_threshold(tmp_path):
    xlsx_path = tmp_path / "sample_run.xlsx"
    create_sample_xlsx(str(xlsx_path))

    # Build a component config dict for C1
    configs = {
        'C1': ComponentConfig(name_raw='C1', display_name='C1', group='Test',
                               max_limit=95.0, warning_limit=80.0, critical_limit=100.0)
    }

    run = load_thermal_run(str(xlsx_path), configs)

    limits_df = evaluate_limits(run, configs)

    # We expect the time above warning (80°C) to be ~15 seconds
    row = limits_df[limits_df['component'] == 'C1'].iloc[0]
    time_above_warning = float(row['time_above_warning'])

    assert math.isclose(time_above_warning, 15.0, rel_tol=1e-3, abs_tol=1e-6), (
        f"Expected ~15s above warning, got {time_above_warning}"
    )

    # There should be 0 seconds above the max_limit (95°C)
    time_above_max = float(row['time_above_max'])
    assert time_above_max == 0.0
