import pandas as pd

from thermal_analyzer.ui.downloads import (
    configuration_csv_bytes,
    configuration_json_bytes,
    sidecar_json_bytes,
)
from thermal_analyzer.ui.components.metadata import (
    apply_campaign_metadata_frame,
    campaign_metadata_frame,
)
from thermal_analyzer.ui.navigation import MODES
from thermal_analyzer.ui.errors import public_error
from thermal_analyzer.ui.state import clear_analysis_state


def test_downloads_are_in_memory_and_portable():
    frame = pd.DataFrame(
        [{"name_raw": "MCU", "display_name": "Controller", "max_limit": 85}]
    )

    assert b"MCU" in configuration_csv_bytes(frame)
    assert b'"name_raw": "MCU"' in configuration_json_bytes(frame)
    sidecar = sidecar_json_bytes("run", "note", {"VAC": 255})
    assert b'"run_id": "run"' in sidecar
    assert b'"notes": "note"' in sidecar


def test_clear_analysis_state_preserves_unrelated_values():
    state = {"campaign_results": object(), "batch_zip": b"zip", "theme": "dark"}
    clear_analysis_state(state)

    assert state == {"theme": "dark"}


def test_navigation_contains_all_supported_modes():
    assert MODES == (
        "Single Run Analysis",
        "Campaign Analysis",
        "Component Comparison",
        "Samples Comparison (A vs B)",
        "File vs File Comparison",
        "Configuration Editor",
    )


def test_campaign_metadata_can_be_reviewed_and_edited(campaign_factory):
    campaign = campaign_factory(
        [("run", {"VAC": 255.0}, (20.0, 30.0, 40.0))]
    )
    frame = campaign_metadata_frame(campaign)
    frame.loc[0, "VAC"] = 210.0
    frame.loc[0, "ambient_temp"] = 50.0
    apply_campaign_metadata_frame(campaign, frame)

    assert campaign.runs[0].metadata == {
        "VAC": 210.0,
        "ambient_temp": 50.0,
    }


def test_public_error_hides_exception_details():
    message = public_error("Unable to process input", ValueError("secret path"))

    assert message.startswith("Unable to process input. Reference:")
    assert "secret path" not in message
