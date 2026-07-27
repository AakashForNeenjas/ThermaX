"""Metadata parsing, manifests, and deterministic campaign matching."""

from .manifest import load_match_overrides, load_metadata_manifest
from .matching import MatchResult, RunMatch, match_campaigns
from .parser import DEFAULT_PATTERNS, parse_metadata

__all__ = [
    "DEFAULT_PATTERNS",
    "MatchResult",
    "RunMatch",
    "load_metadata_manifest",
    "load_match_overrides",
    "match_campaigns",
    "parse_metadata",
]
