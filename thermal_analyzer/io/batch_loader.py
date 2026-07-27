import os
import json
import logging
from typing import Dict, Iterable, Tuple

from ..models import TestCampaign, ComponentConfig
from ..config import DEFAULT_TIME_COLUMN
from ..utils.naming import parse_metadata_from_filename
from .excel_loader import load_thermal_run, load_thermal_run_from_bytes

logger = logging.getLogger(__name__)


def _list_excel_files(folder_path: str):
    """Recursively find all .xlsx files in a folder."""
    excel_files = []
    for root, _dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".xlsx"):
                excel_files.append(os.path.join(root, file))
    return excel_files


def _load_sidecar_metadata(excel_path: str) -> dict:
    """
    Load optional sidecar JSON file alongside an Excel file.
    The sidecar must share the same base name: e.g. run1.xlsx → run1.json.
    Any keys in the JSON override the filename-parsed metadata.
    The special key 'notes' populates run.notes.
    """
    json_path = os.path.splitext(excel_path)[0] + ".json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read sidecar JSON {json_path}: {e}")
    return {}


def load_campaign_from_folder(
    folder_path: str,
    component_configs: Dict[str, ComponentConfig],
    time_column: str = DEFAULT_TIME_COLUMN,
) -> TestCampaign:
    """
    Load all thermal runs from a folder into a TestCampaign.
    Also loads optional .json sidecar files for additional metadata/notes.
    """
    files = _list_excel_files(folder_path)
    runs = []

    logger.info(f"Found {len(files)} Excel files in {folder_path}")

    for f in files:
        try:
            run = load_thermal_run(f, component_configs, time_column)

            # Parse metadata from filename, then overlay sidecar (sidecar wins)
            meta = parse_metadata_from_filename(run.run_id)
            sidecar = _load_sidecar_metadata(f)
            run.metadata.update(meta)
            run.metadata.update({k: v for k, v in sidecar.items() if k != "notes"})
            if "notes" in sidecar:
                run.notes = sidecar["notes"]

            runs.append(run)
        except Exception as e:
            logger.error(f"Failed to load {f}: {e}")

    return TestCampaign(runs=runs)


def load_campaign_from_uploads(
    files: Iterable[Tuple[str, bytes]],
    component_configs: Dict[str, ComponentConfig],
    time_column: str = DEFAULT_TIME_COLUMN,
) -> tuple[TestCampaign, Dict[str, str]]:
    """
    Load a campaign from browser-uploaded Excel files.

    ``files`` contains ``(filename, content)`` pairs. Filename metadata is
    parsed in the same way as folder campaigns. A mapping of skipped filenames
    to their error messages is returned so the UI can report partial failures.
    """
    runs = []
    errors: Dict[str, str] = {}

    for file_name, file_bytes in files:
        try:
            run = load_thermal_run_from_bytes(
                file_bytes,
                file_name,
                component_configs,
                time_column,
            )
            run.metadata.update(parse_metadata_from_filename(run.run_id))
            runs.append(run)
        except Exception as exc:
            logger.error("Failed to load uploaded file %s: %s", file_name, exc)
            errors[file_name] = str(exc)

    return TestCampaign(runs=runs), errors
