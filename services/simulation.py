"""
Core simulation loop for the DLMP ABM Stochastic Scenario Lab.

Orchestrates:
  1. MATLAB or Python RNG scenario generation.
  2. Per-scenario agent instantiation and AC OPF market clearing.
  3. Collection of bus, branch, generator, and summary results.
  4. Optional RUNPF validation per scenario.
  5. OLS econometric regression on the aggregated results.
  6. Result caching and response construction.
"""

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pandapower as pp
from fastapi import HTTPException

from agents.market_operator import MarketOperator
from utils.data_io import load_config_from_dataframe, sample_by_pdf

import services.state as state
from services.matlab_runner import generate_scenarios_via_matlab
from services.validation import validate_scenario
from services.regressions import run_ols_models
from services.plot_builder import build_plot_data, build_overview_plots


def _sanitize(obj):
    """
    Recursively convert numpy scalar types to Python native types so that
    FastAPI's jsonable_encoder can serialise the response without errors.
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj



def run_simulation(params) -> dict:
    """
    Execute the full stochastic scenario simulation pipeline and return
    a JSON-serialisable result dict suitable for the /api/simulate endpoint.

    Args:
        params: SimulationParams pydantic model instance.

    Returns:
        Dict containing logs, summary statistics, OLS results, plot data,
        preview tables, and validation diagnostics.
    """
    # Seed Python RNG deterministically
    import random
    random.seed(params.random_seed)
    np.random.seed(params.random_seed)

    summary_rows: list = []
    bus_results_all: list = []
    branch_results_all: list = []
    gen_results_all: list = []
    validation_rows: list = []

    # -----------------------------------------------------------------------
    # Phase 1: Scenario generation (MATLAB or Python RNG)
    # -----------------------------------------------------------------------
    use_matlab = False
    matlab_scenarios: list = []

    if params.scenario_generator == "matlab":
        try:
            print("Attempting MATLAB background scenario generation...")
            matlab_scenarios = generate_scenarios_via_matlab(params, state.global_config_df)
            use_matlab = True
            print(f"Successfully generated {len(matlab_scenarios)} scenarios via MATLAB.")
        except Exception as ex:
            print(f"MATLAB scenario generation unavailable (falling back to Python RNG): {ex}")
    else:
        print("Python RNG scenario generation selected by user.")
        np.random.seed(params.random_seed)

    sim_logs = [
        f"[{_ts()}] Loaded custom bus role config.",
        f"[{_ts()}] Starting case33bw scenario generation. "
        f"Generator: {'MATLAB' if use_matlab else 'Python (RNG)'}, "
        f"Seed: {params.random_seed}"
    ]

    # Pre-load pandapower base net for load reference
    try:
        base_net = pp.networks.case33bw()
        base_loads: dict = {}
        for _, load in base_net.load.iterrows():
            bus_idx = int(load.bus) + 1
            base_loads[bus_idx] = (float(load.p_mw), float(load.q_mvar))
    except Exception:
        base_loads = {}

    # -----------------------------------------------------------------------
    # Phase 2: Main scenario loop
    # -----------------------------------------------------------------------
    valid_count = 0
    total_attempts = 0
    load_scale = 1.0

    while valid_count < params.scenario_count:
        total_attempts += 1

        mo = _create_market_operator(params)

        if use_matlab:
            if valid_count >= len(matlab_scenarios):
                break
            solved, summary, load_scale = _run_matlab_scenario(
                mo, matlab_scenarios[valid_count], params
            )
        else:
            if total_attempts > params.scenario_count * 40:
                raise HTTPException(
                    status_code=500,
                    detail=f"Simülasyon yakınsama hatası. {valid_count} senaryodan sonra çözülemedi."
                )
            solved, summary, load_scale = _run_python_scenario(mo, params)

        if not solved:
            continue

        valid_count += 1
        state.simulation_progress["current"] = valid_count
        sim_logs.append(
            f"[{_ts()}] Generated {valid_count} / {params.scenario_count} "
            f"valid scenarios. Attempts: {total_attempts}"
        )

        # Collect results
        s_buses = _collect_bus_results(valid_count, mo)
        s_branches = _collect_branch_results(valid_count, mo)
        s_gens = _collect_gen_results(valid_count, mo)

        bus_results_all.extend(s_buses)
        branch_results_all.extend(s_branches)
        gen_results_all.extend(s_gens)

        s_summary = _build_summary_row(
            valid_count, total_attempts, params, summary,
            load_scale, mo, s_buses, s_branches, s_gens
        )
        summary_rows.append(s_summary)

        # RUNPF validation (optional)
        if params.run_validation:
            if valid_count == 1:
                sim_logs.append(f"[{_ts()}] RUNPF validation started.")
            val_row = validate_scenario(valid_count, mo.net)
            validation_rows.append(val_row)

    # -----------------------------------------------------------------------
    # Phase 3: Post-processing
    # -----------------------------------------------------------------------
    df_sum = pd.DataFrame(summary_rows)

    ols_results = run_ols_models(df_sum, params.scenario_count)

    # Cache in-memory for /api/download-results
    state.latest_simulation_data = {
        "summary_rows": summary_rows,
        "bus_results_all": bus_results_all,
        "branch_results_all": branch_results_all,
        "gen_results_all": gen_results_all,
        "validation_rows": validation_rows,
        "global_config_df": (
            state.global_config_df.copy() if state.global_config_df is not None else None
        )
    }

    if params.run_validation:
        sim_logs.append(f"[{_ts()}] RUNPF validation completed.")
    sim_logs.append(f"[{_ts()}] Done. Simulation completed successfully.")

    plot_data = build_plot_data(
        df_sum, bus_results_all,
        params.plot_bus_a, params.plot_bus_b, params.plot_bus_c
    )
    overview_plots = build_overview_plots(
        df_sum, bus_results_all, branch_results_all,
        params.plot_bus_a, params.plot_bus_b, params.plot_bus_c
    )

    val_fail_reasons: dict = {}
    if validation_rows:
        df_val = pd.DataFrame(validation_rows)
        val_fail_reasons = {
            str(k): int(v)
            for k, v in df_val[df_val["validation_pass"] == 0]["dominant_fail_reason"]
            .value_counts().items()
        }

    return _sanitize({
        "status": "success",
        "logs": sim_logs,
        "summary": {
            "objective_cost": float(df_sum["objective_cost"].mean()),
            "total_load_MW": float(df_sum["total_Pd_MW"].mean()),
            "total_loss_MW": float(df_sum["total_P_loss_MW"].mean()),
            "cost_to_load_total": float(df_sum["cost_to_load_total"].mean())
        },
        "ols_results": ols_results,
        "buses": bus_results_all,
        "branches": branch_results_all,
        "generators": gen_results_all,
        "validation_table": validation_rows,
        "plot_data": plot_data,
        "overview_plots": overview_plots,
        "validation_fail_reasons": val_fail_reasons,
        "summary_table": summary_rows
    })



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime('%H:%M:%S')


def _create_market_operator(params) -> MarketOperator:
    mo = MarketOperator()
    mo.grid_c2 = params.grid_c2
    mo.grid_c1 = params.grid_c1
    mo.grid_c0 = params.grid_c0
    mo.set_environment(params.season, params.case_time)
    return mo


def _run_python_scenario(mo: MarketOperator, params) -> tuple:
    """Run one scenario using Python RNG via MarketOperator."""
    load_scale = sample_by_pdf(
        params.global_load_scale_range[0],
        params.global_load_scale_range[1],
        params.global_load_scale_pdf
    )
    mo.environment["global_load_scale"] = load_scale
    mo.environment["prosumer_policy"] = params.prosumer_policy

    temp_config = state.global_config_df.copy()
    try:
        load_config_from_dataframe(temp_config, mo, pdf_name=params.offer_pdf)
        summary = mo.run_market()
        return True, summary, load_scale
    except Exception as e:
        import traceback
        print(f"[DEBUG] _run_python_scenario failed: {e}")
        traceback.print_exc()
        return False, {}, load_scale


def _run_matlab_scenario(mo: MarketOperator, s: dict, params) -> tuple:
    """Apply a pre-generated MATLAB scenario to the MarketOperator and solve OPF."""
    load_scale = float(s["global_load_scale"])
    mo.environment["global_load_scale"] = load_scale
    mo.environment["prosumer_policy"] = params.prosumer_policy

    load_config_from_dataframe(state.global_config_df, mo, pdf_name=params.offer_pdf)

    mo.net = pp.networks.case33bw()
    mo.net.poly_cost.at[0, 'cp2_eur_per_mw2'] = mo.grid_c2
    mo.net.poly_cost.at[0, 'cp1_eur_per_mw'] = mo.grid_c1
    mo.net.poly_cost.at[0, 'cp0_eur'] = mo.grid_c0

    # Set exact loads from MATLAB scenario
    for b_idx in range(33):
        pd_val = float(s["Pd"][b_idx])
        qd_val = float(s["Qd"][b_idx])
        load_rows = mo.net.load[mo.net.load.bus == b_idx]
        if not load_rows.empty:
            mo.net.load.at[load_rows.index[0], 'p_mw'] = pd_val
            mo.net.load.at[load_rows.index[0], 'q_mvar'] = qd_val
        else:
            pp.create_load(mo.net, bus=b_idx, p_mw=pd_val, q_mvar=qd_val)

    # Build generators from MATLAB scenario
    gen_buses = s["gen_bus"]
    if isinstance(gen_buses, (int, float)):
        gen_buses = [gen_buses]
    else:
        gen_buses = list(gen_buses)

    mo.agent_gen_map = {}
    for g_idx, bus_id_1 in enumerate(gen_buses):
        bus_id = int(bus_id_1)
        bus_idx = bus_id - 1

        def _scalar(arr, i):
            return float(arr[i]) if hasattr(arr, "__len__") else float(arr)

        pmin = _scalar(s["gen_pmin"], g_idx)
        pmax = _scalar(s["gen_pmax"], g_idx)
        qmin = _scalar(s["gen_qmin"], g_idx)
        qmax = _scalar(s["gen_qmax"], g_idx)
        c2 = _scalar(s["gen_c2"], g_idx)
        c1 = _scalar(s["gen_c1"], g_idx)
        c0 = _scalar(s["gen_c0"], g_idx)

        if bus_id == 1:
            mo.net.ext_grid.at[0, 'min_p_mw'] = pmin
            mo.net.ext_grid.at[0, 'max_p_mw'] = pmax
            mo.net.ext_grid.at[0, 'min_q_mvar'] = qmin
            mo.net.ext_grid.at[0, 'max_q_mvar'] = qmax
        else:
            gen_idx = pp.create_gen(
                mo.net, bus=bus_idx, p_mw=0.0,
                min_p_mw=pmin, max_p_mw=pmax,
                min_q_mvar=qmin, max_q_mvar=qmax,
                controllable=True
            )
            mo.agent_gen_map[bus_id] = gen_idx
            pp.create_poly_cost(
                mo.net, element=gen_idx, et="gen",
                cp1_eur_per_mw=c1, cp2_eur_per_mw2=c2, cp0_eur=c0
            )

    # Apply agent voltage limits
    for agent in mo.agents.values():
        bus_idx = agent.bus_id - 1
        if hasattr(agent, "Vmin_pu") and agent.Vmin_pu is not None:
            mo.net.bus.at[bus_idx, 'min_vm_pu'] = agent.Vmin_pu
        if hasattr(agent, "Vmax_pu") and agent.Vmax_pu is not None:
            mo.net.bus.at[bus_idx, 'max_vm_pu'] = agent.Vmax_pu

    # Dynamic slack limits
    tot_p = mo.net.load.p_mw.sum()
    tot_q = mo.net.load.q_mvar.sum()
    limit_p = max(10.0, 2.0 * tot_p)
    limit_q = max(10.0, 2.0 * tot_q)
    mo.net.ext_grid.at[0, 'min_p_mw'] = 0.0
    mo.net.ext_grid.at[0, 'max_p_mw'] = limit_p
    mo.net.ext_grid.at[0, 'min_q_mvar'] = -limit_q
    mo.net.ext_grid.at[0, 'max_q_mvar'] = limit_q
    mo.net.ext_grid['controllable'] = len(mo.agent_gen_map) == 0

    try:
        pp.runopp(mo.net, solver='mips')
    except Exception:
        return False, {}, load_scale

    # Update agent states from solved network
    _update_agent_states(mo)

    total_c2l = sum(
        agent.C2L for agent in mo.agents.values() if hasattr(agent, "C2L")
    )
    summary = {
        "objective_cost": float(mo.net.res_cost),
        "total_load_MW": float(mo.net.load.p_mw.sum()),
        "total_loss_MW": float(mo.net.res_line.pl_mw.sum()),
        "grid_Pg_MW": float(mo.net.res_ext_grid.p_mw.iloc[0]),
        "grid_Qg_MVAr": float(mo.net.res_ext_grid.q_mvar.iloc[0]),
        "cost_to_load_total": total_c2l
    }
    return True, summary, load_scale


def _update_agent_states(mo: MarketOperator):
    """Populate agent result attributes from the solved pandapower network."""
    for agent in mo.agents.values():
        bus_idx = agent.bus_id - 1
        agent.V_actual = float(mo.net.res_bus.at[bus_idx, 'vm_pu'])
        agent.theta_actual = float(mo.net.res_bus.at[bus_idx, 'va_degree'])
        agent.DLMP_active = float(mo.net.res_bus.at[bus_idx, 'lam_p'])
        agent.DLMP_reactive = (
            float(mo.net.res_bus.at[bus_idx, 'lam_q'])
            if 'lam_q' in mo.net.res_bus.columns else 0.0
        )

        if agent.bus_id == 1:
            agent.Pg_dispatched = float(mo.net.res_ext_grid.at[0, 'p_mw'])
            agent.Qg_dispatched = float(mo.net.res_ext_grid.at[0, 'q_mvar'])
            agent.Pd_total = 0.0
            agent.Qd_total = 0.0
        else:
            load_rows = mo.net.load[mo.net.load.bus == bus_idx]
            if not load_rows.empty:
                agent.Pd_total = float(mo.net.load.at[load_rows.index[0], 'p_mw'])
                agent.Qd_total = float(mo.net.load.at[load_rows.index[0], 'q_mvar'])
            else:
                agent.Pd_total = 0.0
                agent.Qd_total = 0.0

            if agent.bus_id in mo.agent_gen_map:
                gen_idx = mo.agent_gen_map[agent.bus_id]
                agent.Pg_dispatched = float(mo.net.res_gen.at[gen_idx, 'p_mw'])
                agent.Qg_dispatched = float(mo.net.res_gen.at[gen_idx, 'q_mvar'])
            else:
                agent.Pg_dispatched = 0.0
                agent.Qg_dispatched = 0.0

        agent.netLoad = agent.Pd_total - agent.Pg_dispatched
        agent.C2L = agent.netLoad * agent.DLMP_active


def _collect_bus_results(scenario_id: int, mo: MarketOperator) -> list:
    rows = []
    for agent_id, agent in mo.agents.items():
        pd_mw = getattr(agent, "Pd_total", 0.0)
        qd_mvar = getattr(agent, "Qd_total", 0.0)
        pg_mw = getattr(agent, "Pg_dispatched", 0.0)
        qg_mvar = getattr(agent, "Qg_dispatched", 0.0)
        net_load = getattr(agent, "netLoad", pd_mw)
        cost_to_load = getattr(agent, "C2L", getattr(agent, "C2L_net", 0.0))

        cls_name = agent.__class__.__name__
        if agent_id.startswith("slack_"):
            role_name = "Slack/Grid"
        elif cls_name == "LoadAgent":
            role_name = "PQ Load"
        elif cls_name == "DERAgent":
            role_name = "DER"
        elif cls_name == "ProsumerAgent":
            role_name = "Prosumer"
        else:
            role_name = cls_name.replace("Agent", "")

        rows.append({
            "scenario_id": scenario_id,
            "bus_id": agent.bus_id,
            "role": role_name,
            "Pd_MW": pd_mw,
            "Qd_MVAr": qd_mvar,
            "added_Pd_MW": getattr(agent, "Pd_added", 0.0),
            "added_Qd_MVAr": (
                getattr(agent, "Pd_added", 0.0)
                * math.tan(math.acos(agent.pf))
                if (hasattr(agent, "Pd_added") and getattr(agent, "pf", 1.0) < 1.0)
                else 0.0
            ),
            "Pg_MW": pg_mw,
            "Qg_MVAr": qg_mvar,
            "net_load_MW": net_load,
            "Vm_pu": agent.V_actual,
            "Va_deg": agent.theta_actual,
            "DLMP_LAM_P": agent.DLMP_active,
            "DLMP_LAM_Q": agent.DLMP_reactive,
            "cost_to_load": cost_to_load
        })

    return sorted(rows, key=lambda x: x["bus_id"])


def _collect_branch_results(scenario_id: int, mo: MarketOperator) -> list:
    rows = []
    if not (hasattr(mo, "net") and mo.net is not None):
        return rows

    net = mo.net
    for idx, row in net.line.iterrows():
        from_bus = int(row["from_bus"]) + 1
        to_bus = int(row["to_bus"]) + 1
        p_from = float(net.res_line.at[idx, "p_from_mw"])
        p_to = float(net.res_line.at[idx, "p_to_mw"])
        q_from = float(net.res_line.at[idx, "q_from_mvar"])
        q_to = float(net.res_line.at[idx, "q_to_mvar"])

        rows.append({
            "scenario_id": scenario_id,
            "branch_id": idx + 1,
            "from_bus": from_bus,
            "to_bus": to_bus,
            "Pf_MW": p_from,
            "Pt_MW": p_to,
            "Qf_MVAr": q_from,
            "Qt_MVAr": q_to,
            "P_loss_MW": abs(p_from + p_to),
            "Q_loss_MVAr": abs(q_from + q_to),
            "rateA_MVA": float(row["max_i_ka"]),
            "loading_percent": float(net.res_line.at[idx, "loading_percent"])
        })
    return rows


def _collect_gen_results(scenario_id: int, mo: MarketOperator) -> list:
    rows = []
    gen_counter = 0
    for agent in mo.agents.values():
        if agent.__class__.__name__ in ("DERAgent", "ProsumerAgent", "SlackGridAgent"):
            gen_counter += 1
            rows.append({
                "scenario_id": scenario_id,
                "gen_id": gen_counter,
                "bus_id": agent.bus_id,
                "Pg_MW": getattr(agent, "Pg_dispatched", 0.0),
                "Qg_MVAr": getattr(agent, "Qg_dispatched", 0.0),
                "Pmin_MW": getattr(agent, "Pmin", 0.0),
                "Pmax_MW": getattr(agent, "Pmax", 0.0),
                "Qmin_MVAr": getattr(agent, "Qmin", 0.0),
                "Qmax_MVAr": getattr(agent, "Qmax", 0.0),
                "Vg_pu": getattr(agent, "V_actual", 1.0),
                "status": 1,
                "c2": getattr(agent, "c2", 0.0),
                "c1": getattr(agent, "c1", 0.0),
                "c0": getattr(agent, "c0", 0.0)
            })
    return rows


def _build_summary_row(
    valid_count: int,
    total_attempts: int,
    params,
    summary: dict,
    load_scale: float,
    mo: MarketOperator,
    s_buses: list,
    s_branches: list,
    s_gens: list
) -> dict:
    slack_agent = mo.agents.get(f"slack_1")
    grid_pg = slack_agent.Pg_dispatched if slack_agent else summary.get("grid_Pg_MW", 0.0)
    grid_qg = slack_agent.Qg_dispatched if slack_agent else summary.get("grid_Qg_MVAr", 0.0)

    local_gen_mw = sum(b["Pg_MW"] for b in s_buses if b["role"] in ("DER", "Prosumer"))
    local_gen_share = local_gen_mw / max(1e-9, grid_pg + local_gen_mw)

    dlmp_P_list = [b["DLMP_LAM_P"] for b in s_buses]
    dlmp_Q_list = [b["DLMP_LAM_Q"] for b in s_buses]

    return {
        "scenario_id": valid_count,
        "opf_success": 1,
        "objective_cost": summary["objective_cost"],
        "attempt_no": total_attempts - valid_count + 1,
        "N_requested": params.scenario_count,
        "global_load_scale_pdf": params.global_load_scale_pdf,
        "offer_pdf": params.offer_pdf,
        "case_time": params.case_time,
        "season": params.season,
        "time_generation_multiplier": mo.environment.get("time_generation_multiplier", 1.0),
        "season_demand_multiplier": mo.environment.get("season_demand_multiplier", 1.0),
        "prosumer_policy": params.prosumer_policy,
        "global_load_scale": load_scale,
        "total_Pd_MW": summary["total_load_MW"],
        "total_Qd_MVAr": sum(b["Qd_MVAr"] for b in s_buses),
        "total_added_Pd_MW": sum(b["added_Pd_MW"] for b in s_buses),
        "total_added_Qd_MVAr": sum(b["added_Qd_MVAr"] for b in s_buses),
        "total_P_loss_MW": summary["total_loss_MW"],
        "total_Q_loss_MVAr": sum(l["Q_loss_MVAr"] for l in s_branches),
        "max_branch_loading_percent": (
            max(l["loading_percent"] for l in s_branches) if s_branches else 0.0
        ),
        "mean_DLMP_LAM_P": float(np.mean(dlmp_P_list)),
        "DLMP_spread_LAM_P": max(dlmp_P_list) - min(dlmp_P_list),
        "mean_DLMP_LAM_Q": float(np.mean(dlmp_Q_list)),
        "DLMP_spread_LAM_Q": max(dlmp_Q_list) - min(dlmp_Q_list),
        "out_grid_Pg_MW": grid_pg,
        "out_grid_Qg_MVAr": grid_qg,
        "local_generation_MW": local_gen_mw,
        "local_generation_share": local_gen_share,
        "cost_to_load_total": summary["cost_to_load_total"],
        "number_of_DER_buses": sum(1 for b in s_buses if b["role"] == "DER"),
        "number_of_prosumer_buses": sum(1 for b in s_buses if b["role"] == "Prosumer")
    }
