import pandapower as pp
import pandapower.networks as pn
import pandas as pd
import numpy as np

class MarketOperator:
    """
    Piyasa Operatörü (MO) / Koordinatör Ajanı.
    Fiziksel şebeke modelini yükler, ajanları koordine eder,
    AC OPF piyasa takasını gerçekleştirir ve sonuçları dağıtır.
    """
    def __init__(self, grid_c2=0.020, grid_c1=80.0, grid_c0=0.0):
        self.grid_c2 = float(grid_c2)
        self.grid_c1 = float(grid_c1)
        self.grid_c0 = float(grid_c0)
        
        self.agents = {} # agent_id -> Agent nesnesi
        self.environment = {
            "season": "Kış",
            "case_time": "Öğle",
            "season_demand_multiplier": 1.0,
            "time_generation_multiplier": 1.0
        }
        self.net = None
        self.agent_gen_map = {} # bus_id -> gen_index in pandapower

    def add_agent(self, agent):
        """
        Sisteme yeni bir düğüm ajanı ekler.
        """
        self.agents[agent.id] = agent

    def clear_agents(self):
        """
        Tüm ajanları temizler.
        """
        self.agents = {}
        self.agent_gen_map = {}

    def set_environment(self, season, case_time):
        """
        Küresel ortam değişkenlerini kaydeder ve çarpanları hesaplar.
        """
        self.environment["season"] = str(season)
        self.environment["case_time"] = str(case_time)
        
        # Mevsimsel yük çarpanı (Yaz için 1.2, Kış için 1.0)
        if season == "Yaz":
            self.environment["season_demand_multiplier"] = 1.2
        else:
            self.environment["season_demand_multiplier"] = 1.0
            
        # Zamansal üretim kapasite çarpanı
        case_time_lower = case_time.lower()
        if "gece" in case_time_lower:
            self.environment["time_generation_multiplier"] = 0.0
        elif "önce" in case_time_lower: # Öğleden önce
            self.environment["time_generation_multiplier"] = 0.4
        elif "öğle" in case_time_lower:
            self.environment["time_generation_multiplier"] = 1.0
        elif "akşam" in case_time_lower or "üstü" in case_time_lower:
            self.environment["time_generation_multiplier"] = 0.6
        else:
            self.environment["time_generation_multiplier"] = 1.0

    def run_market(self):
        """
        1. Aşama Kural Tabanlı Piyasa Takasını (AC OPF) gerçekleştirir.
        """
        # 1. Base 33-Bus şebekesini sıfırdan yükle
        self.net = pn.case33bw()
        self.agent_gen_map = {}
        
        # Pandapower OPF için ext_grid'in controllable olması zorunludur
        self.net.ext_grid['controllable'] = True
        
        # 2. Slack (Grid) maliyet katsayılarını güncelle

        # ext_grid elemanı her zaman index 0'dadır.
        self.net.poly_cost.at[0, 'cp2_eur_per_mw2'] = self.grid_c2
        self.net.poly_cost.at[0, 'cp1_eur_per_mw'] = self.grid_c1
        self.net.poly_cost.at[0, 'cp0_eur'] = self.grid_c0
        
        # 3. Ajan tekliflerini topla ve şebekeye uygula
        for agent_id, agent in self.agents.items():
            offer = agent.get_offer(self.environment)
            bus_idx = agent.bus_id - 1  # 0-indexed mapping
            # --- Gerilim Sınırları Güncellemesi ---
            if hasattr(agent, "Vmin_pu") and agent.Vmin_pu is not None:
                self.net.bus.at[bus_idx, 'min_vm_pu'] = agent.Vmin_pu

            if hasattr(agent, "Vmax_pu") and agent.Vmax_pu is not None:
                self.net.bus.at[bus_idx, 'max_vm_pu'] = agent.Vmax_pu
                
            # --- Tüketim Yükü Güncellemesi ---

            if "Pd_total" in offer:
                # Düğümdeki mevcut load elemanını bul
                load_rows = self.net.load[self.net.load.bus == bus_idx]
                if not load_rows.empty:
                    # Mevcut yükü ajan teklifine göre güncelle
                    load_idx = load_rows.index[0]
                    self.net.load.at[load_idx, 'p_mw'] = offer["Pd_total"]
                    self.net.load.at[load_idx, 'q_mvar'] = offer["Qd_total"]
                else:
                    # Eğer yük yoksa yeni oluştur
                    pp.create_load(self.net, bus=bus_idx, p_mw=offer["Pd_total"], q_mvar=offer["Qd_total"])
                    
            # --- Üretici Yeteneği (Generator) Ekleme ---
            if agent.bus_id == 1:
                # Slack/Grid parametreleri döngü sonrasında toplu olarak dinamik ayarlanacaktır.
                pass


            elif offer["role"] in ["DER", "Prosumer"]:
                # DER/Prosumer barası için yeni bir generator tanımla
                gen_idx = pp.create_gen(
                    self.net, 
                    bus=bus_idx, 
                    p_mw=0.0, 
                    min_p_mw=offer["Pmin"], 
                    max_p_mw=offer["Pmax"], 
                    min_q_mvar=offer["Qmin"], 
                    max_q_mvar=offer["Qmax"], 
                    controllable=True
                )
                self.agent_gen_map[agent.bus_id] = gen_idx
                
                # Üretim maliyet eğrisini tanımla
                pp.create_poly_cost(
                    self.net, 
                    element=gen_idx, 
                    et="gen", 
                    cp1_eur_per_mw=offer["c1"], 
                    cp2_eur_per_mw2=offer["c2"], 
                    cp0_eur=offer["c0"]
                )



        # 3.5. Slack (Grid) kapasite sınırlarını dinamik ayarla ve controllable durumunu güncelle
        tot_p = self.net.load.p_mw.sum()
        tot_q = self.net.load.q_mvar.sum()
        limit_p = max(10.0, 2.0 * tot_p)
        limit_q = max(10.0, 2.0 * tot_q)
        
        self.net.ext_grid.at[0, 'min_p_mw'] = 0.0
        self.net.ext_grid.at[0, 'max_p_mw'] = limit_p
        self.net.ext_grid.at[0, 'min_q_mvar'] = -limit_q
        self.net.ext_grid.at[0, 'max_q_mvar'] = limit_q
        
        # Eğer yerel jeneratörler varsa, ext_grid controllable=False yapılarak kararsızlık önlenir.
        has_local_gens = len(self.agent_gen_map) > 0
        self.net.ext_grid['controllable'] = not has_local_gens

        # 4. AC OPF Çözümünü çalıştır (PandaPower & IPOPT)

        try:
            pp.runopp(self.net, solver='ipopt')
            success = True
        except Exception as e:
            print(f"[ERROR] AC OPF failed to converge: {e}")
            try:
                import os
                debug_path = os.path.abspath("debug_opf_failed.txt")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(f"Exception: {e}\n\n")
                    f.write("=== ext_grid ===\n")
                    f.write(self.net.ext_grid.to_string() + "\n\n")
                    f.write("=== load ===\n")
                    f.write(self.net.load.to_string() + "\n\n")
                    f.write("=== gen ===\n")
                    f.write(self.net.gen.to_string() + "\n\n")
                    f.write("=== bus limits ===\n")
                    f.write(self.net.bus[['min_vm_pu', 'max_vm_pu']].to_string() + "\n\n")
                    f.write("=== poly_cost ===\n")
                    f.write(self.net.poly_cost.to_string() + "\n\n")
                print(f"[DEBUG] Wrote OPF failure diagnostics to: {debug_path}")
            except Exception as ex:
                print(f"[DEBUG] Failed to write diagnostics file: {ex}")
            success = False
            
        if not success:
            raise RuntimeError("PandaPower AC OPF çözümü yakınsayamadı!")

        # 5. Mutabakat Sonuçlarını Ajanlara Geri Dağıt (Settlement)
        for agent_id, agent in self.agents.items():
            bus_idx = agent.bus_id - 1
            
            # Gerilim ve Konumsal Fiyatları (DLMP) al
            V_actual = self.net.res_bus.vm_pu.loc[bus_idx]
            theta_actual = self.net.res_bus.va_degree.loc[bus_idx]
            DLMP_active = self.net.res_bus.lam_p.loc[bus_idx]
            DLMP_reactive = self.net.res_bus.lam_q.loc[bus_idx]
            
            if agent.bus_id == 1:
                # Slack / Grid jeneratörü dispatçleri ext_grid tablosundan alınır
                Pg_disp = self.net.res_ext_grid.p_mw.iloc[0]
                Qg_disp = self.net.res_ext_grid.q_mvar.iloc[0]
                
                agent.set_settlement(
                    V_actual=V_actual, 
                    theta_actual=theta_actual, 
                    DLMP_active=DLMP_active, 
                    DLMP_reactive=DLMP_reactive,
                    Pg_dispatched=Pg_disp, 
                    Qg_dispatched=Qg_disp
                )
            elif agent.bus_id in self.agent_gen_map:
                # DER veya Prosumer için Pg ve Qg üretim dispatçlerini al
                gen_idx = self.agent_gen_map[agent.bus_id]
                Pg_disp = self.net.res_gen.p_mw.loc[gen_idx]
                Qg_disp = self.net.res_gen.q_mvar.loc[gen_idx]
                
                agent.set_settlement(
                    V_actual=V_actual, 
                    theta_actual=theta_actual, 
                    DLMP_active=DLMP_active, 
                    DLMP_reactive=DLMP_reactive,
                    Pg_dispatched=Pg_disp, 
                    Qg_dispatched=Qg_disp
                )
            else:
                # Sadece Load ajanı ise
                agent.set_settlement(
                    V_actual=V_actual, 
                    theta_actual=theta_actual, 
                    DLMP_active=DLMP_active, 
                    DLMP_reactive=DLMP_reactive
                )

        # 6. Sistem Özet İstatistiklerini Derle
        total_load_mw = self.net.res_load.p_mw.sum()
        total_loss_mw = self.net.res_line.pl_mw.sum()
        objective_cost = self.net.res_cost
        
        # Dış şebeke (Grid/Slack) dispatçleri
        grid_pg = self.net.res_ext_grid.p_mw.iloc[0]
        grid_qg = self.net.res_ext_grid.q_mvar.iloc[0]
        
        # Toplam tüketici maliyeti (C2L)
        total_c2l = 0.0
        for agent in self.agents.values():
            if hasattr(agent, "C2L"):
                total_c2l += agent.C2L
            elif hasattr(agent, "C2L_net"):
                total_c2l += agent.C2L_net

        return {
            "total_load_MW": total_load_mw,
            "total_loss_MW": total_loss_mw,
            "objective_cost": objective_cost,
            "grid_Pg_MW": grid_pg,
            "grid_Qg_MVAr": grid_qg,
            "cost_to_load_total": total_c2l
        }
