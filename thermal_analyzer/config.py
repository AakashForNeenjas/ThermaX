import os
import json
import pandas as pd
from typing import Dict
from .models import ComponentConfig

# Global defaults
DEFAULT_TIME_COLUMN = "MCGS_TIME"
DEFAULT_MAX_LIMIT = 110.0
DEFAULT_WARNING_LIMIT = 85.0
DEFAULT_CRITICAL_LIMIT = 120.0
DEFAULT_THRESHOLD_TEMP = 80.0  # Temperature used for time-to-threshold stat in component stats

def load_component_configs(config_path: str) -> Dict[str, ComponentConfig]:
    """
    Load component configurations from a CSV or JSON file.
    Returns a dictionary keyed by 'name_raw'.
    """
    configs = {}
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
        
    if config_path.lower().endswith(".csv"):
        # Use skipinitialspace=True to handle spaces after commas, 
        # but we also need to strip trailing spaces if alignment was used.
        df = pd.read_csv(config_path, skipinitialspace=True)
        
        # Clean header names (remove spaces)
        df.columns = df.columns.str.strip()
        
        # Strip string columns
        df_obj = df.select_dtypes(['object'])
        df[df_obj.columns] = df_obj.apply(lambda x: x.str.strip())
        
        records = df.to_dict(orient="records")
    elif config_path.lower().endswith(".json"):
        with open(config_path, 'r') as f:
            records = json.load(f)
    else:
        raise ValueError("Unsupported config file format. Use .csv or .json")
        
    return component_configs_from_records(records)


def component_configs_from_records(records) -> Dict[str, ComponentConfig]:
    """Build validated component configuration objects from record dictionaries."""
    configs = {}
    for rec in records:
        # Map fields from file to ComponentConfig
        # specific handling for optional fields
        name_raw = rec.get("name_raw")
        if not name_raw:
            continue
            
        if name_raw in configs:
            raise ValueError(f"Duplicate component configuration: {name_raw}")
        max_limit = float(rec.get("max_limit", DEFAULT_MAX_LIMIT))
        warning_limit = float(rec.get("warning_limit", DEFAULT_WARNING_LIMIT))
        critical_limit = float(rec.get("critical_limit", DEFAULT_CRITICAL_LIMIT))
        if not warning_limit <= max_limit <= critical_limit:
            raise ValueError(
                f"Invalid limits for {name_raw}: expected warning <= max <= critical."
            )
        config = ComponentConfig(
            name_raw=name_raw,
            display_name=rec.get("display_name", name_raw),
            group=rec.get("group", "Default"),
            max_limit=max_limit,
            warning_limit=warning_limit,
            critical_limit=critical_limit,
            color_hint=rec.get("color_hint")
        )
        configs[name_raw] = config
    return configs
