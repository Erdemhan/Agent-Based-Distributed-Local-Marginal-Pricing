"""
MATLAB integration service for scenario generation.

Handles:
- Calling MATLAB as a subprocess.
- Generating stochastic scenarios via the MATLAB Engine
  (for seed-identical replication with the reference implementation).
"""

import os
import subprocess
import pandas as pd


def run_matlab_command(cmd: str) -> str:
    """
    Execute a MATLAB batch command in a subprocess and return stdout.

    Args:
        cmd: MATLAB expression to run with -batch flag.

    Returns:
        Captured stdout text.

    Raises:
        RuntimeError: If MATLAB exits with non-zero status.
    """
    try:
        res = subprocess.run(
            ["matlab", "-batch", cmd],
            check=True,
            capture_output=True,
            text=True
        )
        return res.stdout
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr or e.stdout or ""
        raise RuntimeError(f"MATLAB Error: {stderr_msg}")


def generate_scenarios_via_matlab(params, global_config_df: pd.DataFrame) -> list:
    """
    Generate stochastic OPF scenarios using MATLAB for seed-identical
    replication with the MATLAB reference implementation (a_DLMP_v21.m).

    The function:
      1. Reads helper functions from a_DLMP_v21.m (lines after 1947).
      2. Exports global_config_df to a temporary Excel file.
      3. Writes and executes a dynamic MATLAB script.
      4. Loads the resulting .mat file and returns the scenario list.

    Args:
        params: SimulationParams pydantic model with seed, count, PDF etc.
        global_config_df: Bus role configuration DataFrame.

    Returns:
        List of scenario dicts (each containing Pd, Qd, gen arrays).

    Raises:
        FileNotFoundError: If a_DLMP_v21.m is not found.
        RuntimeError: If MATLAB exits with a non-zero return code.
    """
    import scipy.io as sio

    import sys
    
    # Resolve the path of a_DLMP_v21.m using fallbacks
    app_file_path = None
    possible_paths = []
    
    # 1. Bundled inside the PyInstaller temporary folder
    if hasattr(sys, '_MEIPASS'):
        possible_paths.append(os.path.join(sys._MEIPASS, "matlab", "a_DLMP_v21.m"))
    
    # 2. Local matlab folder in workspace
    possible_paths.append(os.path.abspath("matlab/a_DLMP_v21.m"))
    
    # 3. Developer directory (fallback)
    possible_paths.append(os.path.abspath("../tekil-simulasyon/a_DLMP_v21.m"))
    
    for path in possible_paths:
        if os.path.exists(path):
            app_file_path = path
            break
            
    if not app_file_path:
        raise FileNotFoundError(
            f"a_DLMP_v21.m could not be found in any of the search locations: {possible_paths}"
        )
        
    matlab_dir = os.path.dirname(app_file_path)

    with open(app_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    helpers_code = "".join(lines[1946:])

    config_file = os.path.abspath("temp_bus_role_config.xlsx")
    global_config_df.to_excel(config_file, index=False)

    output_mat = os.path.abspath("temp_matlab_scenarios.mat")
    if os.path.exists(output_mat):
        os.remove(output_mat)

    # Season / case time mapping: Python UI values -> MATLAB Turkish strings
    season_map = {"Winter": "Kış", "Summer": "Yaz", "Kış": "Kış", "Yaz": "Yaz"}
    season_mat = season_map.get(params.season, params.season)

    case_time_map = {
        "Night": "Gece", "Morning": "Öğleden önce", "Noon": "Öğle", "Evening": "Akşam üstü",
        "Gece": "Gece",
        "Öğleden önce": "Öğleden önce", "Öğleden Önce": "Öğleden önce",
        "Öğle": "Öğle",
        "Akşam üstü": "Akşam üstü", "Akşam Üstü": "Akşam üstü",
        "Öğleden Sonra": "Öğleden önce"
    }
    case_time_mat = case_time_map.get(params.case_time, params.case_time)

    matlab_script = f"""
addpath('{matlab_dir}');
warning('off', 'all');

try
    roleCfg = readtable('{config_file}');

    cfg = struct();
    cfg.N = {params.scenario_count};
    cfg.globalLoadScaleRange = [{params.global_load_scale_range[0]}, {params.global_load_scale_range[1]}];
    cfg.globalLoadScalePDF = '{params.global_load_scale_pdf}';
    cfg.offerPDF = '{params.offer_pdf}';
    cfg.season = '{season_mat}';
    cfg.caseTime = '{case_time_mat}';
    cfg.prosumerPolicy = '{params.prosumer_policy}';
    cfg.randomSeed = {params.random_seed};

    base_mpc = loadcase('case33bw');
    mpopt = mpoption('verbose', 0, 'out.all', 0);

    rng(cfg.randomSeed, 'twister');

    validCount = 0;
    attempts = 0;
    scenarios = struct();

    while validCount < cfg.N && attempts < {params.scenario_count * 40}
        attempts = attempts + 1;
        try
            [mpc, scenarioInfo] = buildScenarioMPC(base_mpc, roleCfg, cfg);
            results = runopf(mpc, mpopt);
            if isfield(results, 'success') && results.success == 1
                validCount = validCount + 1;

                scenarios(validCount).scenario_id = validCount;
                scenarios(validCount).global_load_scale = scenarioInfo.loadScale;
                scenarios(validCount).Pd = mpc.bus(:, 3);
                scenarios(validCount).Qd = mpc.bus(:, 4);

                scenarios(validCount).gen_bus = mpc.gen(:, 1);
                scenarios(validCount).gen_pmax = mpc.gen(:, 9);
                scenarios(validCount).gen_pmin = mpc.gen(:, 10);
                scenarios(validCount).gen_qmax = mpc.gen(:, 4);
                scenarios(validCount).gen_qmin = mpc.gen(:, 5);

                scenarios(validCount).gen_c2 = mpc.gencost(:, 5);
                scenarios(validCount).gen_c1 = mpc.gencost(:, 6);
                scenarios(validCount).gen_c0 = mpc.gencost(:, 7);
            end
        catch ME
            % Ignore and retry
        end
    end

    if validCount < cfg.N
        error('Could only generate %d of %d scenarios', validCount, cfg.N);
    end

    save('{output_mat}', 'scenarios');
catch ME2
    fprintf('FATAL ERROR: %s\\n', ME2.message);
    exit(1);
end
exit;

{helpers_code}
"""
    script_path = os.path.abspath("generate_scenarios.m")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(matlab_script)

    matlab_script_path_clean = script_path.replace('\\', '/')
    matlab_result = subprocess.run(
        ['matlab', '-batch', f"run('{matlab_script_path_clean}');"],
        capture_output=True,
        text=True
    )

    # Cleanup temp files
    for p in [script_path, config_file]:
        if os.path.exists(p):
            os.remove(p)

    if matlab_result.stdout:
        print(f"[MATLAB STDOUT] {matlab_result.stdout.strip()}")
    if matlab_result.stderr:
        print(f"[MATLAB STDERR] {matlab_result.stderr.strip()}")

    if matlab_result.returncode != 0:
        err_msg = (matlab_result.stdout or matlab_result.stderr or "Unknown MATLAB error")
        raise RuntimeError(
            f"MATLAB exited with code {matlab_result.returncode}: {err_msg.strip()}"
        )

    data = sio.loadmat(output_mat, simplify_cells=True)
    os.remove(output_mat)

    scenarios = data['scenarios']
    if isinstance(scenarios, dict):
        scenarios = [scenarios]
    return scenarios
