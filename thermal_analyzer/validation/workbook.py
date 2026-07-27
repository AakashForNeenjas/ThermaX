"""Workbook, time-axis, and temperature-channel validation."""

import io
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ..config import DEFAULT_TIME_COLUMN
from .models import Severity, ValidatedWorkbook, ValidationReport


def _parse_time_value(value) -> float:
    if pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    try:
        parsed = pd.to_timedelta(str(value))
        return float(parsed.total_seconds())
    except (TypeError, ValueError):
        return float("nan")


def validate_workbook(
    file_name: str,
    content: bytes,
    *,
    time_column: str = DEFAULT_TIME_COLUMN,
    sheet_name: Optional[str] = None,
    component_columns: Optional[Sequence[str]] = None,
    min_rows: int = 2,
    missing_warning_fraction: float = 0.20,
    plausible_temperature_range: tuple[float, float] = (-100.0, 400.0),
) -> ValidatedWorkbook:
    report = ValidationReport(Path(file_name).name)
    if not content:
        report.add(Severity.ERROR, "empty_file", "The uploaded file is empty.")
        return ValidatedWorkbook(file_name, None, time_column, [], None, report)
    if Path(file_name).suffix.lower() != ".xlsx":
        report.add(Severity.ERROR, "unsupported_type", "Only .xlsx files are supported.")
        return ValidatedWorkbook(file_name, None, time_column, [], None, report)

    try:
        workbook = pd.ExcelFile(io.BytesIO(content))
    except Exception:
        report.add(
            Severity.ERROR,
            "unreadable_workbook",
            "The file is not a readable Excel workbook.",
        )
        return ValidatedWorkbook(file_name, None, time_column, [], None, report)

    selected_sheet = sheet_name or workbook.sheet_names[0]
    if selected_sheet not in workbook.sheet_names:
        report.add(
            Severity.ERROR,
            "missing_sheet",
            f"Worksheet '{selected_sheet}' was not found.",
            sheet_name=selected_sheet,
        )
        return ValidatedWorkbook(file_name, selected_sheet, time_column, [], None, report)
    if sheet_name is None and len(workbook.sheet_names) > 1:
        report.add(
            Severity.WARNING,
            "multiple_sheets",
            f"Using the first worksheet; {len(workbook.sheet_names)} worksheets were found.",
            sheet_name=selected_sheet,
        )

    try:
        frame = workbook.parse(selected_sheet)
    except Exception:
        report.add(
            Severity.ERROR,
            "unreadable_sheet",
            f"Worksheet '{selected_sheet}' could not be read.",
            sheet_name=selected_sheet,
        )
        return ValidatedWorkbook(file_name, selected_sheet, time_column, [], None, report)

    if frame.empty:
        report.add(
            Severity.ERROR,
            "empty_sheet",
            "The selected worksheet has no data rows.",
            sheet_name=selected_sheet,
        )
    if len(frame) < min_rows:
        report.add(
            Severity.ERROR,
            "too_few_rows",
            f"At least {min_rows} data rows are required.",
            sheet_name=selected_sheet,
        )
    duplicate_columns = frame.columns[frame.columns.duplicated()].tolist()
    for column in duplicate_columns:
        report.add(
            Severity.ERROR,
            "duplicate_column",
            f"Duplicate column name: {column}",
            sheet_name=selected_sheet,
            column=str(column),
        )
    if time_column not in frame.columns:
        report.add(
            Severity.ERROR,
            "missing_time_column",
            f"Required time column '{time_column}' was not found.",
            sheet_name=selected_sheet,
            column=time_column,
        )

    selected_components = list(component_columns or [
        str(column) for column in frame.columns if column != time_column
    ])
    if not selected_components:
        report.add(
            Severity.ERROR,
            "no_components",
            "No temperature component columns were selected.",
            sheet_name=selected_sheet,
        )

    if time_column in frame.columns:
        parsed_time = frame[time_column].map(_parse_time_value)
        invalid_count = int(parsed_time.isna().sum())
        if invalid_count:
            report.add(
                Severity.ERROR,
                "invalid_time",
                f"{invalid_count} time value(s) could not be parsed.",
                sheet_name=selected_sheet,
                column=time_column,
            )
        valid_time = parsed_time.dropna()
        if valid_time.duplicated().any():
            report.add(
                Severity.WARNING,
                "duplicate_timestamps",
                f"{int(valid_time.duplicated().sum())} duplicate timestamp(s) found.",
                sheet_name=selected_sheet,
                column=time_column,
            )
        if len(valid_time) > 1 and not valid_time.is_monotonic_increasing:
            report.add(
                Severity.ERROR,
                "non_monotonic_time",
                "Time values must be in increasing order.",
                sheet_name=selected_sheet,
                column=time_column,
            )

    low, high = plausible_temperature_range
    usable_components: list[str] = []
    for column in selected_components:
        if column not in frame.columns:
            report.add(
                Severity.ERROR,
                "missing_component",
                f"Selected component '{column}' was not found.",
                sheet_name=selected_sheet,
                column=column,
            )
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.notna().sum() == 0:
            report.add(
                Severity.ERROR,
                "non_numeric_component",
                "Component contains no numeric temperature values.",
                sheet_name=selected_sheet,
                column=column,
            )
            continue
        usable_components.append(column)
        missing_fraction = float(numeric.isna().mean())
        if missing_fraction >= missing_warning_fraction:
            report.add(
                Severity.WARNING,
                "missing_component_data",
                f"{missing_fraction:.0%} of values are missing or non-numeric.",
                sheet_name=selected_sheet,
                column=column,
            )
        if numeric.dropna().std() == 0:
            report.add(
                Severity.WARNING,
                "flat_component",
                "The sensor is constant across the uploaded run.",
                sheet_name=selected_sheet,
                column=column,
            )
        implausible = numeric[(numeric < low) | (numeric > high)]
        if not implausible.empty:
            report.add(
                Severity.WARNING,
                "implausible_temperature",
                f"{len(implausible)} value(s) fall outside {low:g} to {high:g} °C.",
                sheet_name=selected_sheet,
                column=column,
            )

    return ValidatedWorkbook(
        file_name=Path(file_name).name,
        sheet_name=selected_sheet,
        time_column=time_column,
        component_columns=usable_components,
        dataframe=frame,
        report=report,
    )
