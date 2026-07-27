import re
from typing import Dict, Any

def parse_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """
    Extract metadata from filename.
    Pattern example: 255VAC_84VHV_6ALV_50Degree_graph.xlsx
    """
    metadata = {}
    
    # Define regex patterns for common parameters
    patterns = {
        "VAC": r"(\d+)VAC",
        "HV": r"(\d+)VHV",
        "LV_current": r"(\d+)ALV",
        "ambient_temp": r"(\d+)Degree"
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            try:
                metadata[key] = float(match.group(1))
            except ValueError:
                metadata[key] = match.group(1)
                
    return metadata
