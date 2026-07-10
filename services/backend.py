"""
DLMP ABM Stochastic Scenario Lab - FastAPI Backend (Controller Layer)

This file is intentionally thin: it only declares HTTP routes and delegates
all business logic to the services/ package. Follow Single Responsibility
Principle — API routing is the only responsibility of this module.
"""

import io
import os
import shutil

import pandas as pd
import pandapower as pp
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

from utils.data_io import load_config, generate_default_template

import services.state as state
from services.matlab_runner import run_matlab_command
from services.excel_exporter import export_scenarios_to_excel
from services.regressions import run_ols_models
from services.plot_builder import build_plot_data, build_overview_plots
from services.simulation import run_simulation as _run_simulation, _sanitize

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(title="DLMP ABM Stochastic Scenario Lab Backend")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(STATIC_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Default configuration initialisation
# ---------------------------------------------------------------------------

def _init_default_config():
    rows = []
    for bus_id in range(1, 34):
        role = "Slack/Grid" if bus_id == 1 else "PQ Load"
        c2_val = 0.020 if bus_id == 1 else 0.0
        c1_val = 80.0 if bus_id == 1 else 0.0
        rows.append({
            "bus_id": bus_id,
            "role": role,
            "add_Pd_MW": 0.0,
            "pf": 0.95 if bus_id != 1 else 1.0,
            "Vmin_pu": 0.90,
            "Vmax_pu": 1.05,
            "Pmin_MW": 0.0,
            "Pmax_MW": 100.0 if bus_id == 1 else 0.0,
            "Qmin_MVAr": -100.0 if bus_id == 1 else 0.0,
            "Qmax_MVAr": 100.0 if bus_id == 1 else 0.0,
            "c2_min": c2_val,
            "c2_max": c2_val,
            "c1_min": c1_val,
            "c1_max": c1_val,
            "c0": 0.0,
        })
    state.global_config_df = pd.DataFrame(rows)


_init_default_config()


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class BusConfigItem(BaseModel):
    bus_id: int
    role: str
    add_Pd_MW: float
    pf: float
    Vmin_pu: float
    Vmax_pu: float
    Pmin_MW: float
    Pmax_MW: float
    Qmin_MVAr: float
    Qmax_MVAr: float
    c2_min: float
    c2_max: float
    c1_min: float
    c1_max: float
    c0: float


class SimulationParams(BaseModel):
    season: str
    case_time: str
    global_load_scale_pdf: str
    offer_pdf: str
    prosumer_policy: str
    scenario_count: int
    random_seed: int
    global_load_scale_range: List[float]
    run_validation: bool
    grid_c2: float
    grid_c1: float
    grid_c0: float
    output_file_name: str
    plot_bus_a: int
    plot_bus_b: int
    plot_bus_c: int
    scenario_generator: str = "matlab"   # "matlab" | "python"


# ---------------------------------------------------------------------------
# Configuration endpoints
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Return current bus role configuration, refreshing Vmin/Vmax from case33bw."""
    try:
        net = pp.networks.case33bw()
        for idx, row in state.global_config_df.iterrows():
            bus_idx = int(row["bus_id"]) - 1
            state.global_config_df.at[idx, "Vmin_pu"] = float(net.bus.min_vm_pu.loc[bus_idx])
            state.global_config_df.at[idx, "Vmax_pu"] = float(net.bus.max_vm_pu.loc[bus_idx])
    except Exception:
        pass
    return state.global_config_df.to_dict(orient="records")


@app.post("/api/config/update")
def update_config(config_items: List[BusConfigItem]):
    """Overwrite the in-memory configuration with the submitted bus items."""
    rows = [item.model_dump() for item in config_items]
    state.global_config_df = pd.DataFrame(rows)
    return {"status": "success", "message": "Konfigürasyon güncellendi."}


@app.post("/api/config/upload")
async def upload_config_file(file: UploadFile = File(...)):
    """Parse an uploaded Excel or MATLAB .mat config file into global state."""
    import io
    file_bytes = await file.read()

    # Try native Python parsing in-memory first
    try:
        file_stream = io.BytesIO(file_bytes)
        
        # Check if the user accidentally uploaded a results Excel file into the configuration loader
        if file.filename.endswith((".xlsx", ".xls")):
            with pd.ExcelFile(file_stream) as xls:
                if "scenario_dataset" in xls.sheet_names or "bus_results_long" in xls.sheet_names:
                    raise HTTPException(
                        status_code=400,
                        detail="Yüklediğiniz dosya bir 'Simülasyon Sonuç' dosyasıdır. Konfigürasyon yüklemek için lütfen sadece konfigürasyon şablonunu yükleyin veya bu dosyayı sonuç olarak sisteme yüklemek için sağdaki 'Sonuç Excel Yükle' butonunu kullanın."
                    )
            file_stream.seek(0)

        parsed_df = load_config(file_stream, filename=file.filename)
    except HTTPException:
        raise
    except Exception as py_err:
        # Fall back to MATLAB for .mat files if native python fails
        if file.filename.endswith(".mat"):
            temp_path = os.path.abspath(f"temp_upload_{file.filename}")
            with open(temp_path, "wb") as buffer:
                buffer.write(file_bytes)

            temp_excel_path = os.path.abspath("temp_mat_import.xlsx")
            try:
                if os.path.exists(temp_excel_path):
                    try:
                        os.remove(temp_excel_path)
                    except Exception:
                        pass

                matlab_cmd = (
                    f"S = load('{temp_path}'); "
                    f"if isfield(S, 'busRoleConfig') "
                    f"  cfg = S.busRoleConfig; "
                    f"  if isstruct(cfg), cfg = struct2table(cfg); end; "
                    f"  writetable(cfg, '{temp_excel_path}', 'Sheet', 'bus_role_config'); "
                    f"else "
                    f"  error('MAT file does not contain busRoleConfig'); "
                    f"end; "
                    f"exit;"
                )
                run_matlab_command(matlab_cmd)

                if not os.path.exists(temp_excel_path):
                    raise ValueError("MATLAB .mat dosyasını okuyamadı.")

                parsed_df = pd.read_excel(temp_excel_path, sheet_name="bus_role_config")
            except Exception as ml_err:
                raise HTTPException(
                    status_code=400,
                    detail=f"MATLAB dosyası okunamadı (Python Hatası: {py_err} | MATLAB Hatası: {ml_err})"
                )
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                if os.path.exists(temp_excel_path):
                    try:
                        os.remove(temp_excel_path)
                    except Exception:
                        pass
        else:
            raise HTTPException(status_code=400, detail=f"Dosya okuma hatası: {str(py_err)}")

    try:
        required_cols = [
            'bus_id', 'role', 'add_Pd_MW', 'pf', 'Pmin_MW', 'Pmax_MW',
            'Qmin_MVAr', 'Qmax_MVAr', 'Vmin_pu', 'Vmax_pu',
            'c2_min', 'c2_max', 'c1_min', 'c1_max', 'c0'
        ]
        for col in required_cols:
            if col not in parsed_df.columns:
                raise HTTPException(status_code=400, detail=f"Eksik sütun: {col}")

        state.global_config_df = parsed_df
        return state.global_config_df.to_dict(orient="records")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Dosya okuma hatası: {str(e)}")


@app.get("/api/config/download")
def download_config_file(background_tasks: BackgroundTasks):
    """Export the current bus role configuration as a MATLAB .mat file using scipy.io."""
    temp_mat_path = os.path.abspath("bus_role_config.mat")

    if os.path.exists(temp_mat_path):
        try:
            os.remove(temp_mat_path)
        except Exception:
            pass

    try:
        import scipy.io as sio
        import numpy as np

        # Build dict representation of the global config DataFrame
        config_dict = {}
        for col in state.global_config_df.columns:
            if col == "role":
                # MATLAB cell array representation for strings
                config_dict[col] = np.array(state.global_config_df[col].tolist(), dtype=object)
            else:
                config_dict[col] = state.global_config_df[col].values

        mat_data = {
            "busRoleConfig": config_dict,
            "baseCaseName": "case33bw",
            "createdAt": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        sio.savemat(temp_mat_path, mat_data)

        if not os.path.exists(temp_mat_path):
            raise HTTPException(
                status_code=500,
                detail="Failed to generate MAT configuration file."
            )

        def _cleanup():
            if os.path.exists(temp_mat_path):
                try:
                    os.remove(temp_mat_path)
                except Exception:
                    pass

        background_tasks.add_task(_cleanup)
        return FileResponse(
            temp_mat_path,
            filename="bus_role_config.mat",
            media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Konfigürasyon dışa aktarma hatası: {str(e)}")



# ---------------------------------------------------------------------------
# Simulation endpoints
# ---------------------------------------------------------------------------

@app.get("/api/simulate/progress")
def get_simulation_progress():
    """Return the current simulation progress tracker."""
    return state.simulation_progress


@app.post("/api/simulate")
def run_simulation_endpoint(params: SimulationParams):
    """Trigger a full stochastic scenario simulation run."""
    state.simulation_progress["status"] = "running"
    state.simulation_progress["current"] = 0
    state.simulation_progress["total"] = params.scenario_count
    try:
        result = _run_simulation(params)
        state.simulation_progress["status"] = "completed"
        state.simulation_progress["current"] = params.scenario_count
        return result
    except Exception as e:
        state.simulation_progress["status"] = "error"
        raise e


@app.get("/api/sysinfo")
def get_sysinfo():
    """Return system information including startup session ID."""
    return {"startup_id": state.startup_id}


# ---------------------------------------------------------------------------
# Download / upload result endpoints
# ---------------------------------------------------------------------------

@app.get("/api/download-template")
def download_template():
    """Stream a blank Excel configuration template for download."""
    buffer = io.BytesIO()
    generate_default_template(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=varsayilan_sablon.xlsx"}
    )


@app.get("/api/download-results")
def download_results(filename: str = "dlmp_sonuclari.xlsx"):
    """Stream the latest simulation results as an Excel file."""
    if state.latest_simulation_data is None:
        raise HTTPException(
            status_code=404,
            detail="Sonuç bulunamadı. Lütfen önce simülasyonu çalıştırın."
        )

    output_format = "Wide Scenario Format"
    buffer = io.BytesIO()
    export_scenarios_to_excel(
        buffer,
        state.latest_simulation_data["summary_rows"],
        state.latest_simulation_data["bus_results_all"],
        state.latest_simulation_data["branch_results_all"],
        state.latest_simulation_data["gen_results_all"],
        state.latest_simulation_data["validation_rows"],
        state.latest_simulation_data["global_config_df"],
        output_format
    )
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/results/upload")
async def upload_results_file(file: UploadFile = File(...)):
    """
    Load a previously exported Excel results file.
    Restores bus role config, runs OLS regressions, and returns full chart data.
    """
    try:
        import io
        file_bytes = await file.read()
        file_stream = io.BytesIO(file_bytes)

        with pd.ExcelFile(file_stream) as xls:
            if "bus_role_config" in xls.sheet_names:
                state.global_config_df = pd.read_excel(xls, "bus_role_config")
                state.global_config_df.dropna(subset=["bus_id"], inplace=True)

            df_sum = None
            if "scenario_dataset" in xls.sheet_names:
                df_sum = pd.read_excel(xls, "scenario_dataset")
            if "scenario_summary" in xls.sheet_names:
                df_sum = pd.read_excel(xls, "scenario_summary")

            if df_sum is None or df_sum.empty:
                raise ValueError("Geçerli bir senaryo özet sayfası bulunamadı.")

            df_bus = (
                pd.read_excel(xls, "bus_results_long")
                if "bus_results_long" in xls.sheet_names else pd.DataFrame()
            )
            df_branch = (
                pd.read_excel(xls, "branch_results_long")
                if "branch_results_long" in xls.sheet_names else pd.DataFrame()
            )
            df_gen = (
                pd.read_excel(xls, "gen_results_long")
                if "gen_results_long" in xls.sheet_names else pd.DataFrame()
            )
            df_val = (
                pd.read_excel(xls, "runpf_validation")
                if "runpf_validation" in xls.sheet_names else pd.DataFrame()
            )
            has_config = "bus_role_config" in xls.sheet_names

        # Clean and drop rows that are all NaN, format columns
        for df in [df_sum, df_bus, df_branch, df_gen, df_val]:
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                if "scenario_id" in df.columns:
                    df.dropna(subset=["scenario_id"], inplace=True)
                else:
                    df.dropna(how="all", inplace=True)

        # Convert numeric columns to numeric to avoid standard deviation of NaN / range issues
        numeric_cols_sum = [
            "objective_cost", "total_Pd_MW", "total_Qd_MVAr", 
            "total_P_loss_MW", "cost_to_load_total", "DLMP_spread_LAM_P",
            "max_branch_loading_percent", "scenario_id"
        ]
        for col in numeric_cols_sum:
            if col in df_sum.columns:
                df_sum[col] = pd.to_numeric(df_sum[col], errors="coerce")
        df_sum.dropna(subset=["total_Pd_MW"], inplace=True) # Ensure finite range for histogram

        # Cast identifiers to integers for strict matching
        if not df_sum.empty and "scenario_id" in df_sum.columns:
            df_sum["scenario_id"] = pd.to_numeric(df_sum["scenario_id"], errors="coerce").fillna(0).astype(int)
        if not df_bus.empty and "bus_id" in df_bus.columns:
            df_bus["bus_id"] = pd.to_numeric(df_bus["bus_id"], errors="coerce").fillna(0).astype(int)
        if not df_branch.empty and "branch_id" in df_branch.columns:
            df_branch["branch_id"] = pd.to_numeric(df_branch["branch_id"], errors="coerce").fillna(0).astype(int)
        if not df_gen.empty and "bus_id" in df_gen.columns:
            df_gen["bus_id"] = pd.to_numeric(df_gen["bus_id"], errors="coerce").fillna(0).astype(int)

        ols_results = run_ols_models(df_sum, len(df_sum))

        buses_dict = df_bus.to_dict(orient="records")
        branches_dict = df_branch.to_dict(orient="records")
        generators_dict = df_gen.to_dict(orient="records")
        validation_dict = df_val.to_dict(orient="records")

        plot_bus_a, plot_bus_b, plot_bus_c = 2, 17, 33
        plot_data = build_plot_data(df_sum, buses_dict, plot_bus_a, plot_bus_b, plot_bus_c)
        overview_plots = build_overview_plots(
            df_sum, buses_dict, branches_dict,
            plot_bus_a, plot_bus_b, plot_bus_c
        )

        val_fail_reasons: dict = {}
        if not df_val.empty:
            val_fail_reasons = {
                str(k): int(v)
                for k, v in df_val[df_val["validation_pass"] == 0]["dominant_fail_reason"]
                .value_counts().items()
            }

        from datetime import datetime
        ts = datetime.now().strftime('%H:%M:%S')
        upload_logs = [
            f"[{ts}] {'Loaded custom bus role config from results file.' if has_config else 'Ready. Configure bus roles and run.'}",
            f"[{ts}] Loaded results spreadsheet: {file.filename}",
            f"[{ts}] Parsed {len(df_sum)} scenarios successfully.",
            f"[{ts}] {'RUNPF validation results loaded.' if not df_val.empty else 'No RUNPF validation sheet found.'}",
            f"[{ts}] Done. Data loaded and charts updated."
        ]

        return _sanitize({
            "status": "success",
            "logs": upload_logs,
            "summary": {
                "objective_cost": float(df_sum["objective_cost"].mean()),
                "total_load_MW": float(df_sum["total_Pd_MW"].mean()),
                "total_loss_MW": float(df_sum["total_P_loss_MW"].mean()),
                "cost_to_load_total": float(df_sum["cost_to_load_total"].mean())
            },
            "ols_results": ols_results,
            "buses": buses_dict,
            "branches": branches_dict,
            "generators": generators_dict,
            "validation_table": validation_dict,
            "plot_data": plot_data,
            "overview_plots": overview_plots,
            "validation_fail_reasons": val_fail_reasons,
            "summary_table": df_sum.to_dict(orient="records")
        })


    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sonuç yükleme hatası: {str(e)}")


# ---------------------------------------------------------------------------
# Static file serving (must be last)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
