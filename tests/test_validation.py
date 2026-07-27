import io

import pandas as pd

from thermal_analyzer.validation import Severity, validate_workbook


def _workbook_bytes(frame, *, second_sheet=False):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        frame.to_excel(writer, index=False, sheet_name="Data")
        if second_sheet:
            frame.to_excel(writer, index=False, sheet_name="Other")
    return buffer.getvalue()


def test_valid_workbook_passes(excel_bytes_factory):
    validated = validate_workbook("run.xlsx", excel_bytes_factory())

    assert validated.report.is_valid
    assert validated.component_columns == ["MCU"]


def test_missing_time_column_is_blocking(excel_bytes_factory):
    validated = validate_workbook(
        "run.xlsx",
        excel_bytes_factory(time_column="Time"),
    )

    assert not validated.report.is_valid
    assert {issue.code for issue in validated.report.errors} >= {
        "missing_time_column"
    }


def test_time_and_component_quality_issues_are_reported():
    frame = pd.DataFrame(
        {
            "MCGS_TIME": ["00:01:00", "bad", "00:00:00"],
            "Flat": [20, 20, 20],
            "Mixed": [25, "bad", 500],
        }
    )
    validated = validate_workbook("run.xlsx", _workbook_bytes(frame))
    codes = {issue.code for issue in validated.report.issues}

    assert "invalid_time" in codes
    assert "non_monotonic_time" in codes
    assert "flat_component" in codes
    assert "missing_component_data" in codes
    assert "implausible_temperature" in codes


def test_multiple_sheets_warns_and_validation_exports_frame(excel_bytes_factory):
    content = _workbook_bytes(
        pd.DataFrame(
            {"MCGS_TIME": ["00:00:00", "00:01:00"], "MCU": [25, 30]}
        ),
        second_sheet=True,
    )
    validated = validate_workbook("run.xlsx", content)

    assert any(
        issue.severity == Severity.WARNING and issue.code == "multiple_sheets"
        for issue in validated.report.issues
    )
    assert set(validated.report.to_frame().columns) == {
        "severity", "code", "file", "sheet", "column", "message"
    }


def test_explicit_sheet_time_and_component_selection():
    content = _workbook_bytes(
        pd.DataFrame(
            {
                "Elapsed": [0, 60],
                "MCU": [25, 30],
                "Ignore": ["x", "y"],
            }
        ),
        second_sheet=True,
    )
    validated = validate_workbook(
        "run.xlsx",
        content,
        sheet_name="Data",
        time_column="Elapsed",
        component_columns=["MCU"],
    )

    assert validated.report.is_valid
    assert validated.time_column == "Elapsed"
    assert validated.component_columns == ["MCU"]
