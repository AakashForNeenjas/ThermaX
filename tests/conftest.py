import io

import pandas as pd
import pytest

from thermal_analyzer.models import TestCampaign, ThermalRun


@pytest.fixture
def excel_bytes_factory():
    def build(
        temperatures=(25.0, 35.0, 45.0),
        times=("00:00:00", "00:01:00", "00:02:00"),
        *,
        time_column="MCGS_TIME",
        component="MCU",
    ):
        buffer = io.BytesIO()
        pd.DataFrame(
            {time_column: list(times), component: list(temperatures)}
        ).to_excel(buffer, index=False)
        return buffer.getvalue()

    return build


@pytest.fixture
def thermal_run_factory():
    def build(
        values=(20.0, 30.0, 40.0),
        times=(0.0, 60.0, 120.0),
        *,
        run_id="run",
        component="MCU",
        metadata=None,
    ):
        return ThermalRun(
            run_id=run_id,
            file_path=f"{run_id}.xlsx",
            metadata=dict(metadata or {}),
            time=pd.Series(times, dtype=float),
            timestamps=pd.Series([pd.NaT] * len(times)),
            data=pd.DataFrame({component: values}),
        )

    return build


@pytest.fixture
def campaign_factory(thermal_run_factory):
    def build(specs):
        return TestCampaign(
            runs=[
                thermal_run_factory(run_id=run_id, metadata=metadata, values=values)
                for run_id, metadata, values in specs
            ]
        )

    return build
