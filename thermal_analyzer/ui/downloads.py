"""In-memory downloads used by the web UI."""

import json

import pandas as pd


def sidecar_json_bytes(run_id: str, notes: str, metadata: dict) -> bytes:
    data = dict(metadata)
    data["run_id"] = run_id
    data["notes"] = notes
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def configuration_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def configuration_json_bytes(frame: pd.DataFrame) -> bytes:
    return json.dumps(
        frame.to_dict(orient="records"),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
