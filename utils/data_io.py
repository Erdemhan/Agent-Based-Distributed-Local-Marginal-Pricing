import os
import random
import math
import numpy as np
import pandas as pd
import scipy.io as sio
import pandapower as pp
import pandapower.networks as pn

from agents.load_agent import LoadAgent
from agents.der_agent import DERAgent
from agents.prosumer_agent import ProsumerAgent

def truncated_normal(mu, sigma, lower=0.0, upper=1.0):
    """
    [lower, upper] aralığında kesilmiş normal dağılımdan örnek alır.
    """
    for _ in range(200):
        val = random.normalvariate(mu, sigma)
        if lower <= val <= upper:
            return val
    return min(upper, max(lower, mu + sigma * random.normalvariate(0, 1)))

def sample_by_pdf(min_val, max_val, pdf_name="Uniform"):
    """
    MATLAB'deki sampleByPDF fonksiyonunun Python karşılığı.
    c2 ve c1 maliyet sınırlarından olasılık yoğunluk fonksiyonuna göre değer örnekler.
    """
    min_val = float(min_val)
    max_val = float(max_val)
    width = max_val - min_val
    if abs(width) < 1e-9:
        return min_val

    u = random.random()
    x = 0.5 # default

    if pdf_name == "Uniform":
        x = u
    elif pdf_name == "Normal-Truncated":
        x = truncated_normal(0.5, 1.0/6.0)
    elif pdf_name == "Triangular":
        if u < 0.5:
            x = math.sqrt(0.5 * u)
        else:
            x = 1.0 - math.sqrt(0.5 * (1.0 - u))
    elif pdf_name == "Beta(2,2)-Bounded":
        # Bounded beta(2,2)
        g1 = -math.log(max(1e-300, random.random() * random.random()))
        g2 = -math.log(max(1e-300, random.random() * random.random()))
        x = g1 / (g1 + g2) if (g1 + g2) > 0 else 0.5
    elif pdf_name == "Lognormal-Truncated":
        sigma = 0.35
        mu = math.log(0.45)
        for _ in range(200):
            cand = math.exp(mu + sigma * random.normalvariate(0, 1))
            if 0.0 <= cand <= 1.0:
                x = cand
                break
        else:
            x = min(1.0, max(0.0, mu + sigma * random.normalvariate(0, 1)))
    elif pdf_name == "Two-Peak Mixture":
        if random.random() < 0.5:
            x = truncated_normal(0.28, 0.10)
        else:
            x = truncated_normal(0.72, 0.10)
            
    return min_val + width * min(1.0, max(0.0, x))


def load_config(file_path):
    """
    Excel (.xlsx) veya MATLAB (.mat) dosyasından bara rollerini ve ayarlarını yükler
    ve temizlenmiş bir pandas DataFrame döndürür.
    """
    df = None
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.xlsx', '.xls']:
        xls = pd.ExcelFile(file_path)
        sheet_name = 'bus_role_config' if 'bus_role_config' in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        
    elif ext == '.mat':
        mat_data = sio.loadmat(file_path)
        if 'busRoleConfig' in mat_data:
            mat_struct = mat_data['busRoleConfig']
            names = mat_struct.dtype.names
            data_dict = {}
            for name in names:
                col_data = mat_struct[name][0, 0]
                if col_data.dtype.kind in ['U', 'S']:
                    data_dict[name] = [str(x[0]).strip() if len(x) > 0 else "" for x in col_data]
                else:
                    data_dict[name] = col_data.flatten()
            df = pd.DataFrame(data_dict)
        else:
            raise ValueError("MAT dosyası içerisinde 'busRoleConfig' değişkeni bulunamadı!")
    else:
        raise ValueError(f"Desteklenmeyen dosya formatı: {ext}")

    df.columns = [c.strip() for c in df.columns]
    return df


def load_config_from_dataframe(df, market_operator, pdf_name="Uniform"):
    """
    Özelleştirilmiş / Düzenlenmiş DataFrame girdisini okuyarak Ajanları oluşturur
    ve MarketOperator'e kaydeder.
    """
    market_operator.clear_agents()
    
    # 1. Base 33-Bus şebekesindeki varsayılan yükleri (base load) çıkar
    base_net = pn.case33bw()
    base_loads = {} # bus_id -> (p_mw, q_mvar)
    for _, load in base_net.load.iterrows():
        bus_id = int(load.bus) + 1
        base_loads[bus_id] = (float(load.p_mw), float(load.q_mvar))

    # DataFrame kolon adlarını temizle ve standartlaştır
    df.columns = [c.strip() for c in df.columns]

    # 2. Satır satır okuyarak Ajanları oluştur
    for _, row in df.iterrows():
        bus_id = int(row['bus_id'])
        role = str(row['role']).strip()
        
        add_Pd_MW = float(row.get('add_Pd_MW', 0.0))
        pf = float(row.get('pf', 0.90))
        Vmin_pu = float(row.get('Vmin_pu', 0.90))
        Vmax_pu = float(row.get('Vmax_pu', 1.05))
        
        Pmin_MW = float(row.get('Pmin_MW', 0.0))
        Pmax_MW = float(row.get('Pmax_MW', 0.0))
        Qmin_MVAr = float(row.get('Qmin_MVAr', 0.0))
        Qmax_MVAr = float(row.get('Qmax_MVAr', 0.0))
        
        c2_min = float(row.get('c2_min', 0.0))
        c2_max = float(row.get('c2_max', 0.0))
        c1_min = float(row.get('c1_min', 0.0))
        c1_max = float(row.get('c1_max', 0.0))
        c0 = float(row.get('c0', 0.0))
        
        c2 = sample_by_pdf(c2_min, c2_max, pdf_name)
        c1 = sample_by_pdf(c1_min, c1_max, pdf_name)

        Pd_base, Qd_base = base_loads.get(bus_id, (0.0, 0.0))

        if role == "PQ Load":
            agent = LoadAgent(
                agent_id=f"load_{bus_id}",
                bus_id=bus_id,
                Pd_base=Pd_base,
                Qd_base=Qd_base,
                Pd_added=add_Pd_MW,
                pf=pf,
                Vmin_pu=Vmin_pu,
                Vmax_pu=Vmax_pu
            )
            market_operator.add_agent(agent)
            
        elif role == "DER":
            agent = DERAgent(
                agent_id=f"der_{bus_id}",
                bus_id=bus_id,
                Pmin_base=Pmin_MW,
                Pmax_base=Pmax_MW,
                Qmin_base=Qmin_MVAr,
                Qmax_base=Qmax_MVAr,
                c2=c2,
                c1=c1,
                c0=c0,
                Vmin_pu=Vmin_pu,
                Vmax_pu=Vmax_pu
            )
            market_operator.add_agent(agent)
            
        elif role == "Prosumer":
            agent = ProsumerAgent(
                agent_id=f"prosumer_{bus_id}",
                bus_id=bus_id,
                Pd_base=Pd_base,
                Qd_base=Qd_base,
                Pd_added=add_Pd_MW,
                pf=pf,
                Pmin_base=Pmin_MW,
                Pmax_base=Pmax_MW,
                Qmin_base=Qmin_MVAr,
                Qmax_base=Qmax_MVAr,
                c2=c2,
                c1=c1,
                c0=c0,
                Vmin_pu=Vmin_pu,
                Vmax_pu=Vmax_pu
            )
            market_operator.add_agent(agent)
            
        elif role == "Slack/Grid":
            market_operator.grid_c2 = c2
            market_operator.grid_c1 = c1
            market_operator.grid_c0 = c0
            
            agent = DERAgent(
                agent_id=f"slack_{bus_id}",
                bus_id=bus_id,
                Pmin_base=Pmin_MW,
                Pmax_base=Pmax_MW,
                Qmin_base=Qmin_MVAr,
                Qmax_base=Qmax_MVAr,
                c2=c2,
                c1=c1,
                c0=c0,
                Vmin_pu=Vmin_pu,
                Vmax_pu=Vmax_pu
            )
            market_operator.add_agent(agent)



def export_to_excel(file_path, market_operator, summary_metrics):
    """
    Simülasyon sonuçlarını orijinal MATLAB formatındaki sayfa yapılarıyla
    birebir uyumlu olacak şekilde Excel dosyasına yazar.
    """
    net = market_operator.net
    
    # --- 1. sweep_summary Sayfası ---
    summary_data = {
        "scenario_id": [1],
        "case_time": [market_operator.environment["case_time"]],
        "season": [market_operator.environment["season"]],
        "season_demand_multiplier": [market_operator.environment["season_demand_multiplier"]],
        "time_generation_multiplier": [market_operator.environment["time_generation_multiplier"]],
        "objective_cost": [summary_metrics["objective_cost"]],
        "cost_to_load_total": [summary_metrics["cost_to_load_total"]],
        "total_Pd_MW": [summary_metrics["total_load_MW"]],
        "total_P_loss_MW": [summary_metrics["total_loss_MW"]],
        "grid_Pg_MW": [summary_metrics["grid_Pg_MW"]],
        "grid_Qg_MVAr": [summary_metrics["grid_Qg_MVAr"]]
    }
    df_summary = pd.DataFrame(summary_data)

    # --- 2. bus_results_long Sayfası ---
    bus_rows = []
    for agent_id, agent in market_operator.agents.items():
        bus_rows.append({
            "scenario_id": 1,
            "bus_id": agent.bus_id,
            "role": agent.__class__.__name__.replace("Agent", ""), # Load, DER, Prosumer
            "Vm_pu": agent.V_actual,
            "Va_degree": agent.theta_actual,
            "Pd_MW": getattr(agent, "Pd_total", 0.0),
            "Qd_MVAr": getattr(agent, "Qd_total", 0.0),
            "DLMP_active": agent.DLMP_active,
            "DLMP_reactive": agent.DLMP_reactive,
            "cost_to_load": getattr(agent, "C2L", getattr(agent, "C2L_net", 0.0))
        })
    df_bus = pd.DataFrame(bus_rows).sort_values("bus_id")

    # --- 3. gen_results_long Sayfası ---
    gen_rows = []
    # Slack generator
    slack_rows = market_operator.net.ext_grid
    if not slack_rows.empty:
        # Slack bus is 1 (index 0)
        grid_bus_id = int(slack_rows.bus.iloc[0]) + 1
        gen_rows.append({
            "scenario_id": 1,
            "gen_id": 1,
            "bus_id": grid_bus_id,
            "role": "Slack/Grid",
            "Pg_MW": summary_metrics["grid_Pg_MW"],
            "Qg_MVAr": summary_metrics["grid_Qg_MVAr"],
            "c2": market_operator.grid_c2,
            "c1": market_operator.grid_c1,
            "c0": market_operator.grid_c0
        })

    # Diğer generator ajanları (DER ve Prosumer)
    gen_id_counter = 2
    for agent_id, agent in market_operator.agents.items():
        if hasattr(agent, "Pg_dispatched") and agent.__class__.__name__ != "SlackAgent":
            if agent.id.startswith("slack_"):
                continue # Slack already added
            gen_rows.append({
                "scenario_id": 1,
                "gen_id": gen_id_counter,
                "bus_id": agent.bus_id,
                "role": agent.__class__.__name__.replace("Agent", ""),
                "Pg_MW": agent.Pg_dispatched,
                "Qg_MVAr": agent.Qg_dispatched,
                "c2": agent.c2,
                "c1": agent.c1,
                "c0": agent.c0
            })
            gen_id_counter += 1
    df_gen = pd.DataFrame(gen_rows)

    # --- 4. branch_results_long Sayfası ---
    branch_rows = []
    for idx, line in net.line.iterrows():
        res_line = net.res_line.loc[idx]
        branch_rows.append({
            "scenario_id": 1,
            "branch_id": idx + 1,
            "from_bus": int(line.from_bus) + 1,
            "to_bus": int(line.to_bus) + 1,
            "P_from_MW": res_line.p_from_mw,
            "Q_from_MVAr": res_line.q_from_mvar,
            "P_to_MW": res_line.p_to_mw,
            "Q_to_MVAr": res_line.q_to_mvar,
            "P_loss_MW": res_line.pl_mw,
            "Q_loss_MVAr": res_line.ql_mvar,
            "loading_percent": res_line.loading_percent
        })
    df_branch = pd.DataFrame(branch_rows)

    # --- Excel Yazıcı ile Çoklu Sayfaları Kaydet ---
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='sweep_summary', index=False)
        df_bus.to_excel(writer, sheet_name='bus_results_long', index=False)
        df_gen.to_excel(writer, sheet_name='gen_results_long', index=False)
        df_branch.to_excel(writer, sheet_name='branch_results_long', index=False)

    print(f"[INFO] Sonuçlar başarıyla kaydedildi: {file_path}")


def generate_default_template(file_path):
    """
    Kullanıcının özelleştirebilmesi için varsayılan case33bw bara ve rol ayarlarını
    içeren bir Excel şablonu oluşturur.
    """
    rows = []
    # Bus 1: Slack/Grid, Bus 2-33: PQ Load
    for bus_id in range(1, 34):
        role = "Slack/Grid" if bus_id == 1 else "PQ Load"
        
        # Slack bus varsayılan maliyeti: 0.020 / 80 / 0
        c2_val = 0.020 if bus_id == 1 else 0.0
        c1_val = 80.0 if bus_id == 1 else 0.0
        
        rows.append({
            "bus_id": bus_id,
            "role": role,
            "add_Pd_MW": 0.0,
            "pf": 0.90,
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
            "c0": 0.0
        })
        
    df = pd.DataFrame(rows)
    df.to_excel(file_path, sheet_name='bus_role_config', index=False)

