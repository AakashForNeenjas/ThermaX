"""Validation result models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    file_name: str
    sheet_name: Optional[str] = None
    column: Optional[str] = None


@dataclass
class ValidationReport:
    file_name: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == Severity.WARNING]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        sheet_name: Optional[str] = None,
        column: Optional[str] = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                file_name=self.file_name,
                sheet_name=sheet_name,
                column=column,
            )
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "severity": issue.severity.value,
                    "code": issue.code,
                    "file": issue.file_name,
                    "sheet": issue.sheet_name,
                    "column": issue.column,
                    "message": issue.message,
                }
                for issue in self.issues
            ]
        )


@dataclass
class ValidatedWorkbook:
    file_name: str
    sheet_name: Optional[str]
    time_column: str
    component_columns: list[str]
    dataframe: Optional[pd.DataFrame]
    report: ValidationReport
