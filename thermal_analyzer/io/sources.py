"""Portable input sources and upload limits for ThermaX."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from ..config import DEFAULT_TIME_COLUMN
from ..models import ComponentConfig, TestCampaign
from .batch_loader import load_campaign_from_folder, load_campaign_from_uploads


FilePayload = Tuple[str, bytes]


class SourceValidationError(ValueError):
    """Raised when an input source exceeds a safety or portability limit."""


@dataclass(frozen=True)
class UploadLimits:
    max_files: int = 100
    max_file_bytes: int = 50 * 1024 * 1024
    max_total_bytes: int = 250 * 1024 * 1024
    allowed_extensions: tuple[str, ...] = (".xlsx",)


def validate_upload_batch(
    files: Iterable[FilePayload],
    limits: UploadLimits = UploadLimits(),
) -> list[FilePayload]:
    """Validate and materialize an uploaded file batch."""
    payloads = list(files)
    if not payloads:
        raise SourceValidationError("Select at least one Excel file.")
    if len(payloads) > limits.max_files:
        raise SourceValidationError(
            f"Too many files: {len(payloads)} selected; maximum is {limits.max_files}."
        )

    seen: set[str] = set()
    total = 0
    for file_name, content in payloads:
        safe_name = Path(file_name).name
        if safe_name in seen:
            raise SourceValidationError(f"Duplicate filename: {safe_name}")
        seen.add(safe_name)
        if Path(safe_name).suffix.lower() not in limits.allowed_extensions:
            raise SourceValidationError(f"Unsupported file type: {safe_name}")
        if not content:
            raise SourceValidationError(f"Uploaded file is empty: {safe_name}")
        if len(content) > limits.max_file_bytes:
            raise SourceValidationError(
                f"{safe_name} exceeds the {limits.max_file_bytes // (1024 * 1024)} MB limit."
            )
        total += len(content)

    if total > limits.max_total_bytes:
        raise SourceValidationError(
            "Combined uploads exceed the "
            f"{limits.max_total_bytes // (1024 * 1024)} MB campaign limit."
        )
    return [(Path(name).name, content) for name, content in payloads]


@dataclass
class UploadedFileSource:
    files: Sequence[FilePayload]
    limits: UploadLimits = UploadLimits()

    def load(
        self,
        component_configs: dict[str, ComponentConfig],
        time_column: str = DEFAULT_TIME_COLUMN,
    ) -> tuple[TestCampaign, dict[str, str]]:
        payloads = validate_upload_batch(self.files, self.limits)
        return load_campaign_from_uploads(payloads, component_configs, time_column)


@dataclass
class LocalFolderSource:
    path: str

    def load(
        self,
        component_configs: dict[str, ComponentConfig],
        time_column: str = DEFAULT_TIME_COLUMN,
    ) -> tuple[TestCampaign, dict[str, str]]:
        folder = Path(self.path)
        if not folder.is_dir():
            raise SourceValidationError(f"Folder does not exist: {folder}")
        return load_campaign_from_folder(
            str(folder), component_configs, time_column
        ), {}
