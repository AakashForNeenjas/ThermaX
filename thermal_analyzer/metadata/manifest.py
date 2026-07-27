"""Metadata manifest import."""

import io
from pathlib import Path

import pandas as pd


def load_metadata_manifest(content: bytes) -> dict[str, dict]:
    """Load a CSV manifest keyed by normalized filename."""
    if not content:
        raise ValueError("Metadata manifest is empty.")
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("Metadata manifest is not a readable CSV file.") from exc
    if "filename" not in frame.columns:
        raise ValueError("Metadata manifest must contain a 'filename' column.")
    if frame["filename"].isna().any():
        raise ValueError("Metadata manifest contains a blank filename.")

    normalized = frame["filename"].map(lambda value: Path(str(value)).name.casefold())
    if normalized.duplicated().any():
        duplicates = sorted(frame.loc[normalized.duplicated(False), "filename"].astype(str))
        raise ValueError(f"Duplicate manifest filenames: {', '.join(duplicates)}")

    result: dict[str, dict] = {}
    for _, row in frame.iterrows():
        filename = Path(str(row["filename"])).name.casefold()
        result[filename] = {
            key: value
            for key, value in row.drop(labels=["filename"]).to_dict().items()
            if not pd.isna(value)
        }
    return result


def load_match_overrides(content: bytes) -> dict[str, str]:
    """Load explicit Sample A → Sample B run mappings from CSV."""
    if not content:
        return {}
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("Manual match file is not a readable CSV file.") from exc
    required = {"sample_a_run_id", "sample_b_run_id"}
    if not required <= set(frame.columns):
        raise ValueError(
            "Manual match CSV must contain sample_a_run_id and sample_b_run_id."
        )
    if frame[list(required)].isna().any().any():
        raise ValueError("Manual match CSV contains a blank run ID.")
    if frame["sample_a_run_id"].duplicated().any():
        raise ValueError("A Sample A run can only have one manual match.")
    if frame["sample_b_run_id"].duplicated().any():
        raise ValueError("A Sample B run can only have one manual match.")
    return dict(
        zip(
            frame["sample_a_run_id"].astype(str),
            frame["sample_b_run_id"].astype(str),
        )
    )
