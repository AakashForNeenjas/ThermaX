import pytest

from thermal_analyzer.io.sources import (
    SourceValidationError,
    UploadLimits,
    UploadedFileSource,
    validate_upload_batch,
)


def test_upload_limits_reject_duplicates_empty_and_oversize():
    limits = UploadLimits(max_files=2, max_file_bytes=4, max_total_bytes=6)

    with pytest.raises(SourceValidationError, match="Duplicate"):
        validate_upload_batch([("a.xlsx", b"1"), ("a.xlsx", b"2")], limits)
    with pytest.raises(SourceValidationError, match="empty"):
        validate_upload_batch([("a.xlsx", b"")], limits)
    with pytest.raises(SourceValidationError, match="exceeds"):
        validate_upload_batch([("a.xlsx", b"12345")], limits)
    with pytest.raises(SourceValidationError, match="Combined"):
        validate_upload_batch(
            [("a.xlsx", b"1234"), ("b.xlsx", b"1234")], limits
        )


def test_uploaded_source_loads_valid_campaign(excel_bytes_factory):
    source = UploadedFileSource(
        [("255VAC_84VHV_6ALV_50Degree.xlsx", excel_bytes_factory())]
    )
    campaign, errors = source.load({})

    assert errors == {}
    assert len(campaign.runs) == 1
    assert campaign.runs[0].metadata["ambient_temp"] == 50.0
