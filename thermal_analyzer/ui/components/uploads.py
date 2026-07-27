"""Reusable campaign-source controls."""

from typing import Callable

import streamlit as st


def campaign_source_widget(
    label: str,
    key_prefix: str,
    *,
    folder_dialog_available: bool,
    folder_picker: Callable[[str, str], str],
) -> dict:
    """Select a desktop folder or upload multiple Excel files in a browser."""
    if folder_dialog_available:
        source_type = st.radio(
            f"{label} input",
            ["Folder", "Upload Excel files"],
            horizontal=True,
            key=f"{key_prefix}_source_type",
        )
    else:
        source_type = "Upload Excel files"

    manifest_file = st.file_uploader(
        f"{label} metadata manifest (optional CSV)",
        type=["csv"],
        key=f"{key_prefix}_manifest",
        help="CSV columns: filename plus any operating-condition fields.",
    )
    if source_type == "Folder":
        return {
            "type": "folder",
            "path": folder_picker(label, f"{key_prefix}_folder_path"),
            "files": [],
            "manifest": manifest_file,
        }

    uploaded_files = st.file_uploader(
        label,
        type=["xlsx"],
        accept_multiple_files=True,
        key=f"{key_prefix}_uploads",
        help="Select all Excel run files that belong to this campaign.",
    )
    return {
        "type": "uploads",
        "path": "",
        "files": uploaded_files or [],
        "manifest": manifest_file,
    }


def campaign_source_ready(source: dict) -> bool:
    if source["type"] == "folder":
        return bool(source["path"])
    return bool(source["files"])
