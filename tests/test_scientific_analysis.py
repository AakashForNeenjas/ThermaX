import math

import numpy as np
import pandas as pd

from thermal_analyzer.analysis.anomaly import detect_flat_sensors
from thermal_analyzer.analysis.comparisons import get_worst_case_components
from thermal_analyzer.analysis.normalization import (
    compute_derating_curve,
    normalize_to_ambient,
)
from thermal_analyzer.analysis.physics import (
    compute_thermal_resistance,
    compute_time_constants,
)
from thermal_analyzer.analysis.stats import compute_component_stats
from thermal_analyzer.analysis.steady_state import detect_steady_state
from thermal_analyzer.models import ComponentConfig, TestCampaign as Campaign


def test_component_statistics_known_values(thermal_run_factory):
    run = thermal_run_factory(
        values=(20.0, 30.0, 40.0), times=(0.0, 10.0, 20.0)
    )
    row = compute_component_stats(run, threshold_temp=30).iloc[0]

    assert row["min_temp"] == 20.0
    assert row["max_temp"] == 40.0
    assert row["avg_temp"] == 30.0
    assert row["median_temp"] == 30.0
    assert row["max_dTdt"] == 1.0
    assert row["time_of_max"] == 20.0
    assert row["time_to_30C"] == 10.0


def test_steady_state_known_flat_window(thermal_run_factory):
    run = thermal_run_factory(
        values=(40.0, 40.1, 40.1),
        times=(0.0, 60.0, 120.0),
    )
    result = detect_steady_state(
        run, window_minutes=1.0, slope_threshold=0.2
    )

    assert result["steady"]
    assert result["t_steady_state"] == 60.0


def test_thermal_resistance_and_time_constant(thermal_run_factory):
    run = thermal_run_factory(
        values=(20.0, 32.64, 40.0),
        times=(0.0, 60.0, 120.0),
    )
    resistance = compute_thermal_resistance(
        run, power_w=10.0, ambient_temp=20.0
    ).iloc[0]
    time_constant = compute_time_constants(run).iloc[0]

    assert resistance["delta_t"] == 20.0
    assert resistance["R_th (°C/W)"] == 2.0
    assert time_constant["tau (s)"] == 60.0


def test_normalization_and_derating_known_line():
    stats = pd.DataFrame(
        {"component": ["MCU"], "max_temp": [80.0], "avg_temp": [70.0]}
    )
    normalized = normalize_to_ambient(
        stats, measured_ambient=35.0, reference_ambient=25.0
    )
    assert normalized.loc[0, "max_temp_norm"] == 70.0

    comparison = pd.DataFrame(
        {"ambient_temp": [20.0, 30.0, 40.0], "max_temp": [60.0, 70.0, 80.0]}
    )
    summary, curve = compute_derating_curve(comparison, "MCU")
    slope_column = next(column for column in summary if column.startswith("slope"))
    assert summary.loc[0, slope_column] == 1.0
    assert summary.loc[0, "r²"] == 1.0
    assert math.isclose(curve.iloc[-1]["predicted_max_temp"], 80.0)


def test_flat_sensor_and_worst_case(thermal_run_factory):
    flat = thermal_run_factory(values=(30.0, 30.0, 30.0), run_id="flat")
    hot = thermal_run_factory(values=(30.0, 80.0, 90.0), run_id="hot")
    assert detect_flat_sensors(flat) == ["MCU"]

    config = {
        "MCU": ComponentConfig(
            "MCU", "Microcontroller", max_limit=85.0, warning_limit=75.0
        )
    }
    worst = get_worst_case_components(
        Campaign([flat, hot]), config, top_n=1
    )
    assert worst.iloc[0]["run_id"] == "hot"
    assert worst.iloc[0]["margin"] == -5.0
