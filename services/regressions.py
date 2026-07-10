"""
OLS Regression service for DLMP econometric analysis.

Provides a generic Ordinary Least Squares helper and the four
econometric models used in the scenario simulation lab.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple


def simple_ols(
    y: np.ndarray,
    Xraw: np.ndarray,
    names: List[str]
) -> Tuple[str, float, float]:
    """
    Fit an OLS regression: y ~ 1 + X1 + X2 + ... using the Normal Equations.

    Args:
        y:     Dependent variable vector (N,).
        Xraw:  Independent variables matrix (N, K), without intercept column.
        names: Names for each regressor in Xraw.

    Returns:
        Tuple of (coefficient_string, R_squared, RMSE).
    """
    mask = np.isfinite(y) & np.all(np.isfinite(Xraw), axis=1)
    y_clean = y[mask]
    X_clean = Xraw[mask]
    N = len(y_clean)

    if N < len(names) + 1:
        return "N/A", 0.0, 0.0

    X = np.hstack([np.ones((N, 1)), X_clean])

    try:
        beta, _, _, _ = np.linalg.lstsq(X, y_clean, rcond=None)
    except Exception as e:
        return f"Error: {e}", 0.0, 0.0

    y_pred = X @ beta
    residuals = y_clean - y_pred
    sse = np.sum(residuals ** 2)
    sst = np.sum((y_clean - np.mean(y_clean)) ** 2)

    r2 = 1.0 - (sse / sst) if sst > 0 else 0.0
    rmse = np.sqrt(sse / N) if N > 0 else 0.0

    parts = [f"Intercept={beta[0]:.6g}"]
    for idx, name in enumerate(names):
        parts.append(f"{name}={beta[idx + 1]:.6g}")
    coef_str = "; ".join(parts)

    return coef_str, float(r2), float(rmse)


def run_ols_models(df_sum: pd.DataFrame, N: int) -> List[dict]:
    """
    Run the four standard econometric OLS models on the simulation summary.

    Models:
        M1: objective_cost  ~ total_Pd_MW + total_Qd_MVAr + max_branch_loading_percent
        M2: DLMP_spread     ~ total_Pd_MW + total_P_loss_MW + max_branch_loading_percent
        M3: total_P_loss_MW ~ total_Pd_MW + total_Qd_MVAr + local_generation_share
        M4: out_grid_Pg_MW  ~ total_Pd_MW + local_generation_MW + cost_to_load_total

    Args:
        df_sum: DataFrame of scenario summary rows.
        N:      Number of scenarios (for reporting).

    Returns:
        List of dicts with model_id, formula, coefficients, R_squared, RMSE, N.
    """
    m1_coef, m1_r2, m1_rmse = simple_ols(
        df_sum["objective_cost"].values,
        df_sum[["total_Pd_MW", "total_Qd_MVAr", "max_branch_loading_percent"]].values,
        ["total_Pd_MW", "total_Qd_MVAr", "max_branch_loading_percent"]
    )
    m2_coef, m2_r2, m2_rmse = simple_ols(
        df_sum["DLMP_spread_LAM_P"].values,
        df_sum[["total_Pd_MW", "total_P_loss_MW", "max_branch_loading_percent"]].values,
        ["total_Pd_MW", "total_P_loss_MW", "max_branch_loading_percent"]
    )
    m3_coef, m3_r2, m3_rmse = simple_ols(
        df_sum["total_P_loss_MW"].values,
        df_sum[["total_Pd_MW", "total_Qd_MVAr", "local_generation_share"]].values,
        ["total_Pd_MW", "total_Qd_MVAr", "local_generation_share"]
    )
    m4_coef, m4_r2, m4_rmse = simple_ols(
        df_sum["out_grid_Pg_MW"].values,
        df_sum[["total_Pd_MW", "local_generation_MW", "cost_to_load_total"]].values,
        ["total_Pd_MW", "local_generation_MW", "cost_to_load_total"]
    )

    return [
        {
            "model_id": "M1",
            "dependent_variable": "objective_cost",
            "formula": "objective_cost ~ total_Pd + total_Qd + max_loading",
            "coefficients": m1_coef,
            "R_squared": m1_r2,
            "RMSE": m1_rmse,
            "N": N
        },
        {
            "model_id": "M2",
            "dependent_variable": "DLMP_spread_LAM_P",
            "formula": "DLMP_spread ~ total_Pd + losses + max_loading",
            "coefficients": m2_coef,
            "R_squared": m2_r2,
            "RMSE": m2_rmse,
            "N": N
        },
        {
            "model_id": "M3",
            "dependent_variable": "total_P_loss_MW",
            "formula": "losses ~ total_Pd + total_Qd + local_generation_share",
            "coefficients": m3_coef,
            "R_squared": m3_r2,
            "RMSE": m3_rmse,
            "N": N
        },
        {
            "model_id": "M4",
            "dependent_variable": "out_grid_Pg_MW",
            "formula": "grid_dispatch ~ total_Pd + local_generation + C2L",
            "coefficients": m4_coef,
            "R_squared": m4_r2,
            "RMSE": m4_rmse,
            "N": N
        }
    ]
