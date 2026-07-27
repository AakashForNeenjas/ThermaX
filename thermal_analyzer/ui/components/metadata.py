"""Editable campaign metadata tables."""

import pandas as pd


def campaign_metadata_frame(campaign) -> pd.DataFrame:
    fields = sorted(
        {
            field
            for run in campaign.runs
            for field in run.metadata
        }
    )
    return pd.DataFrame(
        [
            {"run_id": run.run_id, **{field: run.metadata.get(field) for field in fields}}
            for run in campaign.runs
        ]
    )


def apply_campaign_metadata_frame(campaign, frame: pd.DataFrame) -> None:
    by_id = {run.run_id: run for run in campaign.runs}
    for record in frame.to_dict(orient="records"):
        run_id = record.pop("run_id")
        if run_id not in by_id:
            continue
        by_id[run_id].metadata = {
            key: value
            for key, value in record.items()
            if not pd.isna(value)
        }
