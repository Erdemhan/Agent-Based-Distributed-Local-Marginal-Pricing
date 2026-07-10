"""
RUNPF (Newton-Raphson Power Flow) consistency validation service.

After each AC OPF solution, this module reconstructs the standard power
flow (runpp) using the OPF-dispatched generator setpoints and compares
voltages, angles, branch flows, and losses to verify physical consistency.
"""

import numpy as np
import pandas as pd
import pandapower as pp

# Tolerance thresholds (matching MATLAB reference)
TOL_VM = 1e-5      # p.u.
TOL_VA = 1e-3      # degrees
TOL_PF = 1e-4      # MW
TOL_QF = 1e-4      # MVAr
TOL_PLOSS = 1e-4   # MW
TOL_QLOSS = 1e-4   # MVAr
TOL_LOADING = 1e-3 # %


def validate_scenario(scenario_id: int, net) -> dict:
    """
    Run RUNPF consistency check on a solved pandapower OPF network object.

    Saves OPF results, then runs standard Newton-Raphson power flow with
    the same generator setpoints and compares the two solutions.

    Args:
        scenario_id: Identifier for the scenario (for reporting).
        net:         Solved pandapower network (after runopp).

    Returns:
        Dict containing validation pass/fail status and per-quantity max errors.
    """
    # 1. Snapshot OPF results before overwriting
    vm_opf = net.res_bus.vm_pu.copy()
    va_opf = net.res_bus.va_degree.copy()
    pl_opf = net.res_line.pl_mw.copy()
    ql_opf = net.res_line.ql_mvar.copy()
    loading_opf = net.res_line.loading_percent.copy()
    pf_opf = net.res_line.p_from_mw.copy()
    qf_opf = net.res_line.q_from_mvar.copy()
    pg_opf_gen = net.res_gen.p_mw.copy() if not net.gen.empty else pd.Series(dtype=float)
    qg_opf_gen = net.res_gen.q_mvar.copy() if not net.gen.empty else pd.Series(dtype=float)
    pg_opf_ext = net.res_ext_grid.p_mw.copy() if not net.ext_grid.empty else pd.Series(dtype=float)
    qg_opf_ext = net.res_ext_grid.q_mvar.copy() if not net.ext_grid.empty else pd.Series(dtype=float)

    # 2. Feed OPF dispatch back as RUNPP setpoints
    if not net.gen.empty:
        net.gen.p_mw = net.res_gen.p_mw
        net.gen.vm_pu = net.res_gen.vm_pu

    success_pf = False
    error_msg = ""
    try:
        pp.runpp(net, algorithm='nr')
        success_pf = net.converged
    except Exception as e:
        success_pf = False
        error_msg = str(e)

    val_row = {
        "scenario_id": scenario_id,
        "runpf_success": 1 if success_pf else 0,
        "validation_pass": 0,
        "dominant_fail_reason": "runpf_fail" if not success_pf else "pass",
        "diagnosis": (
            error_msg if not success_pf
            else "Reconstructed power flow matched OPF outputs."
        ),
        "error_message": error_msg,
        "max_abs_Vm_error": 0.0,
        "max_abs_Va_error": 0.0,
        "max_abs_Pg_error": 0.0,
        "max_abs_Qg_error": 0.0,
        "max_abs_Pf_error": 0.0,
        "max_abs_Qf_error": 0.0,
        "max_abs_Ploss_error": 0.0,
        "max_abs_Qloss_error": 0.0,
        "max_abs_loading_error": 0.0
    }

    if not success_pf:
        return val_row

    # 3. Compute absolute errors per quantity
    vm_err = np.abs(net.res_bus.vm_pu - vm_opf)
    va_err = np.abs(net.res_bus.va_degree - va_opf)
    pf_err = np.abs(net.res_line.p_from_mw - pf_opf)
    qf_err = np.abs(net.res_line.q_from_mvar - qf_opf)
    pl_err = np.abs(net.res_line.pl_mw - pl_opf)
    ql_err = np.abs(net.res_line.ql_mvar - ql_opf)
    loading_err = np.abs(net.res_line.loading_percent - loading_opf)

    pg_err_gen = (
        np.abs(net.res_gen.p_mw - pg_opf_gen)
        if not net.gen.empty else pd.Series([0.0])
    )
    qg_err_gen = (
        np.abs(net.res_gen.q_mvar - qg_opf_gen)
        if not net.gen.empty else pd.Series([0.0])
    )
    pg_err_ext = (
        np.abs(net.res_ext_grid.p_mw - pg_opf_ext)
        if not net.ext_grid.empty else pd.Series([0.0])
    )
    qg_err_ext = (
        np.abs(net.res_ext_grid.q_mvar - qg_opf_ext)
        if not net.ext_grid.empty else pd.Series([0.0])
    )

    val_row["max_abs_Vm_error"] = float(vm_err.max())
    val_row["max_abs_Va_error"] = float(va_err.max())
    val_row["max_abs_Pg_error"] = max(
        float(pg_err_gen.max()) if not pg_err_gen.empty else 0.0,
        float(pg_err_ext.max()) if not pg_err_ext.empty else 0.0
    )
    val_row["max_abs_Qg_error"] = max(
        float(qg_err_gen.max()) if not qg_err_gen.empty else 0.0,
        float(qg_err_ext.max()) if not qg_err_ext.empty else 0.0
    )
    val_row["max_abs_Pf_error"] = float(pf_err.max())
    val_row["max_abs_Qf_error"] = float(qf_err.max())
    val_row["max_abs_Ploss_error"] = float(pl_err.max())
    val_row["max_abs_Qloss_error"] = float(ql_err.max())
    val_row["max_abs_loading_error"] = float(loading_err.max())

    # 4. Evaluate pass/fail per tolerance
    mismatches = []
    if val_row["max_abs_Vm_error"] > TOL_VM:
        mismatches.append("Vm mismatch")
    if val_row["max_abs_Va_error"] > TOL_VA:
        mismatches.append("Va mismatch")
    if val_row["max_abs_Pf_error"] > TOL_PF:
        mismatches.append("Pf mismatch")
    if val_row["max_abs_Qf_error"] > TOL_QF:
        mismatches.append("Qf mismatch")
    if val_row["max_abs_Ploss_error"] > TOL_PLOSS:
        mismatches.append("P-loss mismatch")
    if val_row["max_abs_Qloss_error"] > TOL_QLOSS:
        mismatches.append("Q-loss mismatch")
    if val_row["max_abs_loading_error"] > TOL_LOADING:
        mismatches.append("loading mismatch")

    if mismatches:
        val_row["validation_pass"] = 0
        val_row["dominant_fail_reason"] = mismatches[0]
        val_row["diagnosis"] = f"Validation failed due to: {', '.join(mismatches)}"
    else:
        val_row["validation_pass"] = 1

    return val_row
