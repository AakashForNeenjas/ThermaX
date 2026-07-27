import io

import pandas as pd

from thermal_analyzer.io.batch_loader import load_campaign_from_uploads


def _excel_bytes(temperatures):
    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "MCGS_TIME": ["00:00:00", "00:01:00"],
            "MCU": temperatures,
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


def test_load_campaign_from_uploads_parses_runs_and_filename_metadata():
    campaign, errors = load_campaign_from_uploads(
        [
            ("255VAC_84VHV_6ALV_50Degree_A.xlsx", _excel_bytes([25, 30])),
            ("255VAC_84VHV_6ALV_50Degree_B.xlsx", _excel_bytes([26, 31])),
        ],
        {},
    )

    assert errors == {}
    assert len(campaign.runs) == 2
    assert campaign.runs[0].metadata == {
        "VAC": 255.0,
        "HV": 84.0,
        "LV_current": 6.0,
        "ambient_temp": 50.0,
    }
    assert campaign.runs[0].available_components() == ["MCU"]


def test_load_campaign_from_uploads_reports_bad_files_without_losing_good_runs():
    campaign, errors = load_campaign_from_uploads(
        [
            ("valid.xlsx", _excel_bytes([25, 30])),
            ("invalid.xlsx", b"not an Excel workbook"),
        ],
        {},
    )

    assert len(campaign.runs) == 1
    assert "invalid.xlsx" in errors
