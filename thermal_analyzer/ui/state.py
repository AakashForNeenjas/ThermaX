"""Shared Streamlit session-state helpers."""

from typing import Iterable, MutableMapping


ANALYSIS_STATE_KEYS = (
    "campaign_results",
    "cc_campaign",
    "campaign_report_html",
    "batch_zip",
    "cc_report_html",
    "sab_report_html",
    "fvf_excel",
    "run_report_html",
    "run_report_stats_csv",
    "run_report_limits_csv",
    "limits_cache",
    "steady_cache",
)


def clear_analysis_state(
    state: MutableMapping,
    keys: Iterable[str] = ANALYSIS_STATE_KEYS,
) -> None:
    for key in keys:
        state.pop(key, None)
