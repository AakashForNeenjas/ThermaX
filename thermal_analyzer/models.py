from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import pandas as pd

@dataclass
class ComponentConfig:
    """
    Configuration for a single thermal component.
    Default values below must stay in sync with the DEFAULT_* constants
    in config.py — config.py is the single source of truth for fallback limits.
    """
    name_raw: str
    display_name: str
    group: str = "Default"
    max_limit: float = 110.0      # keep in sync with DEFAULT_MAX_LIMIT
    warning_limit: float = 85.0   # keep in sync with DEFAULT_WARNING_LIMIT
    critical_limit: float = 120.0 # keep in sync with DEFAULT_CRITICAL_LIMIT
    color_hint: Optional[str] = None

@dataclass
class ThermalRun:
    """
    Represents a single thermal test iteration (one Excel file).
    """
    run_id: str
    file_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    time: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    timestamps: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: Optional[str] = None

    def get_component_series(self, name: str) -> pd.Series:
        """Retrieve the temperature series for a specific component."""
        if name in self.data.columns:
            return self.data[name]
        raise KeyError(f"Component '{name}' not found in run '{self.run_id}'.")

    def available_components(self) -> List[str]:
        """List all available component names in this run."""
        return list(self.data.columns)

@dataclass
class TestCampaign:
    """
    Represents a collection of many thermal runs.
    """
    runs: List[ThermalRun] = field(default_factory=list)

    def get_run_by_id(self, run_id: str) -> Optional[ThermalRun]:
        """Find a run by its ID."""
        for run in self.runs:
            if run.run_id == run_id:
                return run
        return None

    def list_components(self) -> set[str]:
        """Return a set of all unique component names across all runs."""
        components = set()
        for run in self.runs:
            components.update(run.available_components())
        return components

    def filter_runs(self, **criteria) -> 'TestCampaign':
        """
        Filter runs based on metadata criteria.
        Example: filter_runs(VAC=255, ambient_temp=50)
        """
        filtered = []
        for run in self.runs:
            match = True
            for key, value in criteria.items():
                if run.metadata.get(key) != value:
                    match = False
                    break
            if match:
                filtered.append(run)
        return TestCampaign(runs=filtered)
