import io

import pandas as pd

from thermal_analyzer.io.excel_loader import load_thermal_run_from_bytes


def test_loader_selects_sheet_and_component_columns():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        pd.DataFrame({"Wrong": [1]}).to_excel(
            writer, sheet_name="Summary", index=False
        )
        pd.DataFrame(
            {
                "Elapsed": [0, 60],
                "MCU": [25, 30],
                "Ignore": [100, 200],
            }
        ).to_excel(writer, sheet_name="Data", index=False)

    run = load_thermal_run_from_bytes(
        buffer.getvalue(),
        "run.xlsx",
        {},
        time_column="Elapsed",
        sheet_name="Data",
        component_columns=["MCU"],
    )

    assert run.available_components() == ["MCU"]
    assert run.time.tolist() == [0.0, 60.0]
