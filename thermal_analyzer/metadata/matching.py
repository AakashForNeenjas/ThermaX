"""Deterministic run matching with explicit ambiguity reporting."""

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from ..models import TestCampaign, ThermalRun


DEFAULT_MATCH_FIELDS = ("VAC", "HV", "LV_current", "ambient_temp")


@dataclass(frozen=True)
class RunMatch:
    run_a: ThermalRun
    run_b: ThermalRun
    signature: tuple
    manual: bool = False


@dataclass
class MatchResult:
    matches: list[RunMatch] = field(default_factory=list)
    unmatched_a: list[ThermalRun] = field(default_factory=list)
    unmatched_b: list[ThermalRun] = field(default_factory=list)
    ambiguous: dict[tuple, tuple[list[ThermalRun], list[ThermalRun]]] = field(
        default_factory=dict
    )


def _signature(run: ThermalRun, fields: Sequence[str]) -> tuple | None:
    if any(field not in run.metadata for field in fields):
        return None
    return tuple((field, run.metadata[field]) for field in fields)


def _group_by_signature(
    runs: Iterable[ThermalRun], fields: Sequence[str]
) -> tuple[dict[tuple, list[ThermalRun]], list[ThermalRun]]:
    grouped: dict[tuple, list[ThermalRun]] = {}
    incomplete: list[ThermalRun] = []
    for run in runs:
        signature = _signature(run, fields)
        if signature is None:
            incomplete.append(run)
            continue
        grouped.setdefault(signature, []).append(run)
    return grouped, incomplete


def match_campaigns(
    campaign_a: TestCampaign,
    campaign_b: TestCampaign,
    fields: Sequence[str] = DEFAULT_MATCH_FIELDS,
    manual_overrides: Mapping[str, str] | None = None,
) -> MatchResult:
    """
    Match campaigns without silently discarding duplicate or partial metadata.

    ``manual_overrides`` maps Sample A run IDs to Sample B run IDs.
    """
    if not fields:
        raise ValueError("Select at least one metadata field for matching.")

    result = MatchResult()
    remaining_a = list(campaign_a.runs)
    remaining_b = list(campaign_b.runs)

    by_id_a = {run.run_id: run for run in remaining_a}
    by_id_b = {run.run_id: run for run in remaining_b}
    for run_a_id, run_b_id in (manual_overrides or {}).items():
        if run_a_id not in by_id_a or run_b_id not in by_id_b:
            raise ValueError(f"Invalid manual match: {run_a_id} → {run_b_id}")
        run_a = by_id_a[run_a_id]
        run_b = by_id_b[run_b_id]
        result.matches.append(RunMatch(run_a, run_b, ("manual",), manual=True))
        remaining_a.remove(run_a)
        remaining_b.remove(run_b)

    grouped_a, incomplete_a = _group_by_signature(remaining_a, fields)
    grouped_b, incomplete_b = _group_by_signature(remaining_b, fields)
    result.unmatched_a.extend(incomplete_a)
    result.unmatched_b.extend(incomplete_b)

    for signature in sorted(set(grouped_a) | set(grouped_b), key=str):
        runs_a = grouped_a.get(signature, [])
        runs_b = grouped_b.get(signature, [])
        if len(runs_a) == 1 and len(runs_b) == 1:
            result.matches.append(RunMatch(runs_a[0], runs_b[0], signature))
        elif runs_a and runs_b:
            result.ambiguous[signature] = (runs_a, runs_b)
        else:
            result.unmatched_a.extend(runs_a)
            result.unmatched_b.extend(runs_b)
    return result
