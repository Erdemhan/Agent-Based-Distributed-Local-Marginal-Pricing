import math
from .base_agent import BaseAgent

class ProsumerAgent(BaseAgent):
    """
    Aynı barada hem elektrik tüketim yükü hem de kontrol edilebilir yerel 
    üretim yeteneği (jeneratör) barındıran hibrit Üretici-Tüketici ajanı.
    """
    def __init__(self, agent_id, bus_id, Pd_base=0.0, Qd_base=0.0, Pd_added=0.0, pf=0.90,
                 Pmin_base=0.0, Pmax_base=0.0, Qmin_base=0.0, Qmax_base=0.0,
                 c2=0.0, c1=0.0, c0=0.0, Vmin_pu=0.90, Vmax_pu=1.05):
        super().__init__(agent_id, bus_id, Vmin_pu, Vmax_pu)
        # Tüketim Parametreleri
        self.Pd_base = float(Pd_base)
        self.Qd_base = float(Qd_base)
        self.Pd_added = float(Pd_added)
        self.pf = float(pf)
        
        # Üretim Parametreleri
        self.Pmin_base = float(Pmin_base)
        self.Pmax_base = float(Pmax_base)
        self.Qmin_base = float(Qmin_base)
        self.Qmax_base = float(Qmax_base)
        self.c2 = float(c2)
        self.c1 = float(c1)
        self.c0 = float(c0)

        # Ölçeklendirilmiş değerler
        self.Pd_total = 0.0
        self.Qd_total = 0.0
        self.Pmin = 0.0
        self.Pmax = 0.0
        self.Qmin = 0.0
        self.Qmax = 0.0

        # Sonuç çıktıları
        self.Pg_dispatched = 0.0
        self.Qg_dispatched = 0.0
        self.netLoad = 0.0
        self.C2L_net = 0.0
        self.Revenue = 0.0
        self.Cost = 0.0
        self.Profit = 0.0

    def get_offer(self, environment):
        """
        Mevsimsel ve zamansal ortam katsayılarına göre tüketim talebini 
        ve üretim sınırlarını eşzamanlı ölçeklendirip teklifini sunar.
        """
        season_mult = environment.get("season_demand_multiplier", 1.0)
        time_mult = environment.get("time_generation_multiplier", 1.0)

        # --- 1. Tüketim Ölçeklendirmesi ---
        added_Qd = 0.0
        if 0 < self.pf <= 1.0:
            if self.pf < 1.0:
                added_Qd = self.Pd_added * math.tan(math.acos(self.pf))
        else:
            raise ValueError(f"Prosumer Ajanı {self.id} için pf (0, 1] aralığında olmalıdır.")

        Pd_configured = self.Pd_base + self.Pd_added
        Qd_configured = self.Qd_base + added_Qd
        
        load_scale = environment.get("global_load_scale", 1.0)
        self.Pd_total = Pd_configured * load_scale * season_mult
        self.Qd_total = Qd_configured * load_scale * season_mult

        # --- 2. Üretim Ölçeklendirmesi ---
        pmin_scaled = self.Pmin_base * time_mult
        pmax_scaled = self.Pmax_base * time_mult
        qmin_scaled = self.Qmin_base * time_mult
        qmax_scaled = self.Qmax_base * time_mult

        policy = environment.get("prosumer_policy", "Feed-in")
        if policy == "Öztüketim":
            final_pd = max(0.0, self.Pd_total)
            pmax_val = max(0.0, pmax_scaled)
            qcap_val = max(abs(qmin_scaled), abs(qmax_scaled))
            smax = math.hypot(pmax_val, qcap_val)

            self.Pmax = min(pmax_val, final_pd)
            self.Pmin = max(0.0, min(pmin_scaled, self.Pmax))

            effective_qcap = math.sqrt(max(0.0, smax**2 - self.Pmax**2))
            self.Qmin = -effective_qcap
            self.Qmax = effective_qcap
        else:
            self.Pmin = pmin_scaled
            self.Pmax = pmax_scaled
            self.Qmin = qmin_scaled
            self.Qmax = qmax_scaled

        # MATLAB guards
        if self.Pmin > self.Pmax:
            self.Pmin = self.Pmax
        if self.Qmin > self.Qmax:
            self.Qmin = self.Qmax

        return {
            "bus_id": self.bus_id,
            "role": "Prosumer",
            "Pd_total": self.Pd_total,
            "Qd_total": self.Qd_total,
            "Pmin": self.Pmin,
            "Pmax": self.Pmax,
            "Qmin": self.Qmin,
            "Qmax": self.Qmax,
            "c2": self.c2,
            "c1": self.c1,
            "c0": self.c0
        }

    def set_settlement(self, V_actual, theta_actual, DLMP_active, DLMP_reactive, Pg_dispatched=0.0, Qg_dispatched=0.0, **kwargs):
        """
        OPF sonuçlarına göre net yükü, şebekeye ödenen faturayı (net C2L), 
        üretim maliyetini ve kârı hesaplar.
        """
        super().set_settlement(V_actual, theta_actual, DLMP_active, DLMP_reactive)
        self.Pg_dispatched = float(Pg_dispatched)
        self.Qg_dispatched = float(Qg_dispatched)

        # Şebekeden çekilen net aktif yük: netLoad = max(Pd - Pg, 0)
        self.netLoad = max(self.Pd_total - self.Pg_dispatched, 0.0)
        
        # Net Fatura maliyeti: netLoad * DLMP_active
        self.C2L_net = self.netLoad * self.DLMP_active

        # Yerel üretim ekonomisi
        self.Revenue = self.Pg_dispatched * self.DLMP_active
        if self.Pg_dispatched > 0.0:
            self.Cost = self.c2 * (self.Pg_dispatched ** 2) + self.c1 * self.Pg_dispatched + self.c0
        else:
            self.Cost = 0.0
        self.Profit = self.Revenue - self.Cost
