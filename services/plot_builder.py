"""
Plot data builder for the DLMP ABM Simulation Lab.

Computes:
  - Histogram data (load distribution, DLMP distributions)
  - Voltage profile (mean/min/max per bus)
  - Branch loading profile (mean per branch)

These are sent to the front-end as JSON for rendering with Chart.js.
"""

import math
import numpy as np
import pandas as pd

from services.histogram import matlab_histogram_bins_fixed, matlab_auto_bins


def build_plot_data(
    df_sum: pd.DataFrame,
    bus_results_all: list,
    plot_bus_a: int,
    plot_bus_b: int,
    plot_bus_c: int
) -> dict:
    """
    Build the econometric scatter plot vectors.

    Args:
        df_sum:          Summary DataFrame (one row per scenario).
        bus_results_all: List of per-bus-per-scenario result dicts.
        plot_bus_a/b/c:  Bus IDs to extract individual DLMP series for.

    Returns:
        Dict of plot vectors ready for JSON serialisation.
    """
    return {
        "scenarios_id": df_sum["scenario_id"].tolist(),
        "total_Pd_MW": df_sum["total_Pd_MW"].tolist(),
        "objective_cost": df_sum["objective_cost"].tolist(),
        "total_P_loss_MW": df_sum["total_P_loss_MW"].tolist(),
        "cost_to_load_total": df_sum["cost_to_load_total"].tolist(),
        "DLMP_spread_LAM_P": df_sum["DLMP_spread_LAM_P"].tolist(),
        "max_branch_loading_percent": (
            df_sum["max_branch_loading_percent"].tolist()
            if "max_branch_loading_percent" in df_sum.columns else []
        ),
        "bus_a_dlmp": [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_a],
        "bus_b_dlmp": [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_b],
        "bus_c_dlmp": [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_c]
    }


def build_overview_plots(
    df_sum: pd.DataFrame,
    bus_results_all: list,
    branch_results_all: list,
    plot_bus_a: int,
    plot_bus_b: int,
    plot_bus_c: int
) -> dict:
    """
    Build overview histogram and profile aggregation data.

    Args:
        df_sum:              Summary DataFrame.
        bus_results_all:     List of per-bus results.
        branch_results_all:  List of per-branch results.
        plot_bus_a/b/c:      Bus IDs for DLMP histogram overlay.

    Returns:
        Dict with histogram bin centres/counts and profile arrays.
    """
    n_bins = max(10, int(math.sqrt(len(df_sum))))

    # Total load demand distribution histogram
    edges_pd = matlab_histogram_bins_fixed(df_sum["total_Pd_MW"].values, n_bins=n_bins)
    counts_pd, _ = np.histogram(df_sum["total_Pd_MW"].values, bins=edges_pd)
    centers_pd = (edges_pd[:-1] + edges_pd[1:]) / 2.0

    # DLMP distribution histograms (three buses overlaid)
    dlmps_a = [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_a]
    dlmps_b = [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_b]
    dlmps_c = [b["DLMP_LAM_P"] for b in bus_results_all if b["bus_id"] == plot_bus_c]

    if dlmps_a:
        bins = matlab_auto_bins(np.array(dlmps_a))
        counts_dlmp_a, _ = np.histogram(dlmps_a, bins=bins)
        counts_dlmp_b, _ = np.histogram(dlmps_b, bins=bins)
        counts_dlmp_c, _ = np.histogram(dlmps_c, bins=bins)
        centers_dlmp = (bins[:-1] + bins[1:]) / 2.0
    else:
        counts_dlmp_a = counts_dlmp_b = counts_dlmp_c = []
        centers_dlmp = []

    # Voltage profile: mean / min / max per bus across all scenarios
    df_bus_all = pd.DataFrame(bus_results_all)
    voltage_profile = []
    for b_id in range(1, 34):
        b_v = (
            df_bus_all[df_bus_all["bus_id"] == b_id]["Vm_pu"].values
            if not df_bus_all.empty else np.array([])
        )
        if len(b_v) == 0:
            voltage_profile.append({"bus_id": b_id, "mean": 1.0, "min": 1.0, "max": 1.0})
        else:
            voltage_profile.append({
                "bus_id": b_id,
                "mean": float(np.mean(b_v)),
                "min": float(np.min(b_v)),
                "max": float(np.max(b_v))
            })

    # Branch loading profile: mean loading per branch across all scenarios
    df_branch_all = pd.DataFrame(branch_results_all)
    branch_profile = []
    for l_id in range(1, 33):
        l_load = (
            df_branch_all[df_branch_all["branch_id"] == l_id]["loading_percent"].values
            if not df_branch_all.empty else np.array([])
        )
        branch_profile.append({
            "branch_id": l_id,
            "mean_loading": float(np.mean(l_load)) if len(l_load) > 0 else 0.0
        })

    return {
        "centers_pd": centers_pd.tolist(),
        "counts_pd": counts_pd.tolist(),
        "centers_dlmp": list(centers_dlmp) if not isinstance(centers_dlmp, list) else centers_dlmp,
        "counts_dlmp_a": list(counts_dlmp_a),
        "counts_dlmp_b": list(counts_dlmp_b),
        "counts_dlmp_c": list(counts_dlmp_c),
        "voltage_profile": voltage_profile,
        "branch_profile": branch_profile
    }
