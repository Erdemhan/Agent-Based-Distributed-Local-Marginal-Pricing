"""
Global in-memory state for the DLMP ABM Simulation Backend.
Centralizes shared mutable state that is accessed across multiple API endpoints.
"""

import pandas as pd

# Active bus role configuration DataFrame
global_config_df: pd.DataFrame | None = None

# Simulation progress tracker (used by /api/simulate/progress polling)
simulation_progress: dict = {
    "status": "idle",
    "current": 0,
    "total": 0
}

# Cache of the most recent simulation results (used for Excel export)
latest_simulation_data: dict | None = None
