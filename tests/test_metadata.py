import pytest

from thermal_analyzer.metadata.manifest import (
    load_match_overrides,
    load_metadata_manifest,
)
from thermal_analyzer.metadata.matching import match_campaigns
from thermal_analyzer.metadata.parser import parse_metadata


def test_parser_supports_decimals_negatives_and_case():
    parsed = parse_metadata("-10.5degree_255.5vac_84vhv_6.25alv.XLSX")

    assert parsed == {
        "VAC": 255.5,
        "HV": 84.0,
        "LV_current": 6.25,
        "ambient_temp": -10.5,
    }


def test_manifest_requires_unique_filenames():
    with pytest.raises(ValueError, match="Duplicate"):
        load_metadata_manifest(
            b"filename,VAC\nrun.xlsx,255\nRUN.xlsx,210\n"
        )


def test_manual_match_csv_requires_one_to_one_mappings():
    assert load_match_overrides(
        b"sample_a_run_id,sample_b_run_id\na1,b1\na2,b2\n"
    ) == {"a1": "b1", "a2": "b2"}

    with pytest.raises(ValueError, match="Sample B"):
        load_match_overrides(
            b"sample_a_run_id,sample_b_run_id\na1,b1\na2,b1\n"
        )


def test_matching_reports_ambiguous_and_incomplete(campaign_factory):
    metadata = {"VAC": 255.0, "ambient_temp": 50.0}
    campaign_a = campaign_factory(
        [
            ("a1", metadata, (20, 30, 40)),
            ("a2", metadata, (21, 31, 41)),
            ("missing", {"VAC": 255.0}, (20, 30, 40)),
        ]
    )
    campaign_b = campaign_factory(
        [
            ("b1", metadata, (22, 32, 42)),
            ("b2", metadata, (23, 33, 43)),
        ]
    )
    result = match_campaigns(
        campaign_a, campaign_b, fields=("VAC", "ambient_temp")
    )

    assert not result.matches
    assert len(result.ambiguous) == 1
    assert [run.run_id for run in result.unmatched_a] == ["missing"]


def test_manual_override_resolves_a_match(campaign_factory):
    campaign_a = campaign_factory([("a", {}, (20, 30, 40))])
    campaign_b = campaign_factory([("b", {}, (21, 31, 41))])
    result = match_campaigns(
        campaign_a,
        campaign_b,
        fields=("VAC",),
        manual_overrides={"a": "b"},
    )

    assert len(result.matches) == 1
    assert result.matches[0].manual
