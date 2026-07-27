from typing import Any, Dict

from ..metadata.parser import parse_metadata

def parse_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """
    Extract metadata from filename.
    Pattern example: 255VAC_84VHV_6ALV_50Degree_graph.xlsx
    """
    return parse_metadata(filename)
