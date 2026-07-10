"""
Excel export service for the DLMP ABM Simulation Lab.

Generates multi-sheet Excel workbooks in either:
  - Wide Scenario Format  (MATLAB-compatible, one row per scenario)
  - Long Format           (one row per bus/branch/gen per scenario)

The wide format column schema is dynamically generated based on bus roles
to exactly match MATLAB's createWideScenarioDataset output.
"""

import os
import pandas as pd
import pandapower as pp


def export_scenarios_to_excel(
    filename,
    summary_rows: list,
    bus_results_all: list,
    branch_results_all: list,
    gen_results_all: list,
    validation_rows: list,
    global_config_df,
    output_format: str
):
    """
    Write simulation results to an Excel file with MATLAB-compatible sheets.

    Args:
        filename:           File path or BytesIO buffer to write to.
        summary_rows:       List of per-scenario summary dicts.
        bus_results_all:    List of per-bus-per-scenario result dicts.
        branch_results_all: List of per-branch-per-scenario result dicts.
        gen_results_all:    List of per-generator-per-scenario result dicts.
        validation_rows:    List of RUNPF validation result dicts (may be empty).
        global_config_df:   Bus role configuration DataFrame.
        output_format:      "Wide Scenario Format" or "Long Format".
    """
    if isinstance(filename, (str, os.PathLike)) and os.path.exists(filename):
        try:
            os.remove(filename)
        except Exception:
            pass

    df_summary = pd.DataFrame(summary_rows)
    df_bus_results = pd.DataFrame(bus_results_all)
    df_branch_results = pd.DataFrame(branch_results_all)
    df_gen_results = pd.DataFrame(gen_results_all)
    df_validation = pd.DataFrame(validation_rows) if validation_rows else pd.DataFrame()

    df_bus_static = _build_bus_static(global_config_df)
    df_branch_static = _build_branch_static()
    df_derived = _build_derived_metrics(df_summary)

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        if output_format == "Wide Scenario Format":
            df_wide = _build_wide_dataset(
                summary_rows, bus_results_all, gen_results_all, global_config_df
            )
            df_wide.to_excel(writer, sheet_name="scenario_dataset", index=False)
            df_summary.to_excel(writer, sheet_name="scenario_summary", index=False)
        else:
            df_summary.to_excel(writer, sheet_name="scenario_dataset", index=False)

        df_bus_results.to_excel(writer, sheet_name="bus_results_long", index=False)
        df_branch_results.to_excel(writer, sheet_name="branch_results_long", index=False)
        df_gen_results.to_excel(writer, sheet_name="gen_results_long", index=False)

        if global_config_df is not None:
            global_config_df.to_excel(writer, sheet_name="bus_role_config", index=False)

        df_bus_static.to_excel(writer, sheet_name="bus_static", index=False)
        df_branch_static.to_excel(writer, sheet_name="branch_static", index=False)
        df_derived.to_excel(writer, sheet_name="derived_metrics", index=False)

        if not df_validation.empty:
            df_validation.to_excel(writer, sheet_name="runpf_validation", index=False)
            _write_validation_summary(writer, df_validation)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_wide_dataset(
    summary_rows: list,
    bus_results_all: list,
    gen_results_all: list,
    global_config_df
) -> pd.DataFrame:
    """
    Build the wide-format scenario dataset matching MATLAB's column order.
    For each DER or Prosumer bus, inserts generator cost/dispatch columns
    immediately after the standard Pd/Qd/Vm/Va/DLMP columns for that bus.
    """
    wide_rows = []
    for s_row in summary_rows:
        s_id = s_row["scenario_id"]

        b1_res = next(
            (b for b in bus_results_all if b["scenario_id"] == s_id and b["bus_id"] == 1),
            None
        )
        bus1_dlmp = b1_res["DLMP_LAM_P"] if b1_res else 0.0

        g1_res = next(
            (g for g in gen_results_all if g["scenario_id"] == s_id and g["bus_id"] == 1),
            None
        )
        grid_c2 = g1_res["c2"] if g1_res else 0.02
        grid_c1 = g1_res["c1"] if g1_res else 80.0

        row_dict = {
            "scenario_id": s_id,
            "out_bus1_DLMP_LAM_P": bus1_dlmp,
            "in_grid_c2": grid_c2,
            "in_grid_c1": grid_c1,
            "out_grid_Pg_MW": s_row["out_grid_Pg_MW"],
            "out_grid_Qg_MVAr": s_row["out_grid_Qg_MVAr"]
        }

        s_gens = [g for g in gen_results_all if g["scenario_id"] == s_id]
        for b_id in range(2, 34):
            b = next(
                (x for x in bus_results_all if x["scenario_id"] == s_id and x["bus_id"] == b_id),
                None
            )
            # Determine role from results or config
            role = "PQ Load"
            if b:
                role = b["role"]
            elif global_config_df is not None:
                role_df = global_config_df[global_config_df["bus_id"] == b_id]
                if not role_df.empty:
                    role = role_df.iloc[0]["role"]

            row_dict[f"in_bus{b_id}_Pd_MW"] = b["Pd_MW"] if b else 0.0
            row_dict[f"in_bus{b_id}_Qd_MVAr"] = b["Qd_MVAr"] if b else 0.0
            row_dict[f"out_bus{b_id}_Vm_pu"] = b["Vm_pu"] if b else 1.0
            row_dict[f"out_bus{b_id}_Va_deg"] = b["Va_deg"] if b else 0.0
            row_dict[f"out_bus{b_id}_DLMP_LAM_P"] = b["DLMP_LAM_P"] if b else 0.0

            if role in ("DER", "Prosumer"):
                prefix = "der" if role == "DER" else "prosumer"
                gr = next((g for g in s_gens if g["bus_id"] == b_id), None)
                row_dict[f"in_{prefix}_bus{b_id}_c2"] = gr["c2"] if gr else 0.0
                row_dict[f"in_{prefix}_bus{b_id}_c1"] = gr["c1"] if gr else 0.0
                row_dict[f"out_{prefix}_bus{b_id}_Pg_MW"] = gr["Pg_MW"] if gr else 0.0
                row_dict[f"out_{prefix}_bus{b_id}_Qg_MVAr"] = gr["Qg_MVAr"] if gr else 0.0

        wide_rows.append(row_dict)

    return pd.DataFrame(wide_rows)


def _build_bus_static(global_config_df) -> pd.DataFrame:
    """Build the static bus parameters table from pandapower case33bw."""
    try:
        base_net = pp.networks.case33bw()
        base_loads: dict = {}
        for _, load in base_net.load.iterrows():
            bus_idx = int(load.bus) + 1
            base_loads[bus_idx] = (float(load.p_mw), float(load.q_mvar))

        rows = []
        for idx, _ in base_net.bus.iterrows():
            bus_id = idx + 1
            role_df = (
                global_config_df[global_config_df["bus_id"] == bus_id]
                if global_config_df is not None
                else pd.DataFrame()
            )
            if not role_df.empty:
                role = role_df.iloc[0]["role"]
                vmin = role_df.iloc[0]["Vmin_pu"]
                vmax = role_df.iloc[0]["Vmax_pu"]
            else:
                role = "Slack/Grid" if bus_id == 1 else "PQ Load"
                vmin = 1.0 if bus_id == 1 else 0.9
                vmax = 1.0 if bus_id == 1 else 1.1

            is_slack = 1 if role == "Slack/Grid" else 0
            is_PV = 1 if role in ("DER", "Prosumer") else 0
            is_PQ = 1 if role == "PQ Load" else 0
            matpower_type = 3 if is_slack else (2 if is_PV else 1)
            pd_base, qd_base = base_loads.get(bus_id, (0.0, 0.0))

            rows.append({
                "bus_id": bus_id,
                "bus_role": role,
                "matpower_bus_type": matpower_type,
                "is_slack": is_slack,
                "is_PQ": is_PQ,
                "is_PV": is_PV,
                "base_Pd_MW": pd_base,
                "base_Qd_MVAr": qd_base,
                "base_kV": 12.66,
                "Vmin_pu": vmin,
                "Vmax_pu": vmax
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _build_branch_static() -> pd.DataFrame:
    """Build the static branch parameters table from pandapower case33bw."""
    Z_BASE = 16.02756  # (12.66 kV)^2 / 10 MVA
    try:
        base_net = pp.networks.case33bw()
        rows = []
        for idx, row in base_net.line.iterrows():
            r_pu = (float(row["r_ohm_per_km"]) * float(row["length_km"])) / Z_BASE
            x_pu = (float(row["x_ohm_per_km"]) * float(row["length_km"])) / Z_BASE
            rows.append({
                "branch_id": float(idx + 1),
                "from_bus": float(row["from_bus"] + 1),
                "to_bus": float(row["to_bus"] + 1),
                "r_pu": r_pu,
                "x_pu": x_pu,
                "b_pu": 0.0,
                "rateA_MVA": 0.0,
                "status": 1.0 if row["in_service"] else 0.0
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _build_derived_metrics(df_summary: pd.DataFrame) -> pd.DataFrame:
    """Extract the derived metrics subset from the summary DataFrame."""
    derived_cols = [
        'scenario_id', 'case_time', 'season', 'time_generation_multiplier',
        'season_demand_multiplier', 'prosumer_policy', 'total_Pd_MW', 'total_Qd_MVAr',
        'objective_cost', 'total_added_Pd_MW', 'total_P_loss_MW', 'total_Q_loss_MVAr',
        'max_branch_loading_percent', 'mean_DLMP_LAM_P', 'DLMP_spread_LAM_P',
        'mean_DLMP_LAM_Q', 'DLMP_spread_LAM_Q', 'out_grid_Pg_MW', 'local_generation_MW',
        'local_generation_share', 'cost_to_load_total', 'number_of_DER_buses',
        'number_of_prosumer_buses'
    ]
    if df_summary.empty:
        return pd.DataFrame()
    available = [c for c in derived_cols if c in df_summary.columns]
    return df_summary[available]


def _write_validation_summary(writer, df_validation: pd.DataFrame):
    """Write the validation_summary aggregation sheet."""
    val_summary = {
        "number_of_rows": [len(df_validation)],
        "number_of_runpf_success": [int(df_validation["runpf_success"].sum())],
        "number_of_runpf_fail": [int((df_validation["runpf_success"] == 0).sum())],
        "number_of_validation_pass": [int(df_validation["validation_pass"].sum())],
        "number_of_validation_mismatch": [int((df_validation["validation_pass"] == 0).sum())],
        "max_abs_Vm_error": [float(df_validation["max_abs_Vm_error"].max())],
        "max_abs_Va_error": [float(df_validation["max_abs_Va_error"].max())],
        "max_abs_Pf_error": [float(df_validation["max_abs_Pf_error"].max())],
        "max_abs_Qf_error": [float(df_validation["max_abs_Qf_error"].max())],
        "max_abs_loading_error": [float(df_validation["max_abs_loading_error"].max())]
    }
    pd.DataFrame(val_summary).to_excel(writer, sheet_name="validation_summary", index=False)
