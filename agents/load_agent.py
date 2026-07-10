import math
from .base_agent import BaseAgent

class LoadAgent(BaseAgent):
    """
    Sadece elektrik tüketimi yapan pasif yük ajanı.
    """
    def __init__(self, agent_id, bus_id, Pd_base=0.0, Qd_base=0.0, Pd_added=0.0, pf=0.90, Vmin_pu=0.90, Vmax_pu=1.05):
        super().__init__(agent_id, bus_id, Vmin_pu, Vmax_pu)
        self.Pd_base = float(Pd_base)   # Şebeke şablonundaki temel aktif yük (MW)
        self.Qd_base = float(Qd_base)   # Şebeke şablonundaki temel reaktif yük (MVAr)
        self.Pd_added = float(Pd_added) # Arayüzden girilen ek aktif yük (MW)
        self.pf = float(pf)             # Ek yükün güç faktörü
        
        # Sonuç çıktıları
        self.Pd_total = 0.0             # Ölçeklendirilmiş toplam aktif yük talebi
        self.Qd_total = 0.0             # Ölçeklendirilmiş toplam reaktif yük talebi
        self.C2L = 0.0                  # Tüketim faturası ($)

    def get_offer(self, environment):
        """
        Küresel mevsim çarpanına göre aktif ve reaktif talebini hesaplar.
        """
        season_mult = environment.get("season_demand_multiplier", 1.0)
        
        # Ek aktif yükten reaktif yük hesaplama: Qd = Pd * tan(acos(pf))
        added_Qd = 0.0
        if 0 < self.pf <= 1.0:
            if self.pf < 1.0:
                added_Qd = self.Pd_added * math.tan(math.acos(self.pf))
        else:
            raise ValueError(f"Ajan {self.id} için güç faktörü (pf) (0, 1] aralığında olmalıdır.")

        # Toplam konfigüre edilen aktif ve reaktif yükler
        Pd_configured = self.Pd_base + self.Pd_added
        Qd_configured = self.Qd_base + added_Qd
        
        # Mevsimsel ve küresel yük ölçeklendirmesi uygulanır
        load_scale = environment.get("global_load_scale", 1.0)
        self.Pd_total = Pd_configured * load_scale * season_mult
        self.Qd_total = Qd_configured * load_scale * season_mult
        
        return {
            "bus_id": self.bus_id,
            "role": "Load",
            "Pd_total": self.Pd_total,
            "Qd_total": self.Qd_total
        }

    def set_settlement(self, V_actual, theta_actual, DLMP_active, DLMP_reactive, **kwargs):
        """
        OPF çözümü sonrası gerilim ve fiyatları günceller ve fatura maliyetini (C2L) hesaplar.
        """
        super().set_settlement(V_actual, theta_actual, DLMP_active, DLMP_reactive)
        
        # Fatura hesabı: C2L = Pd_total * DLMP_active
        # (Elektrik enerjisi aktif fiyat üzerinden faturalandırılır)
        self.C2L = self.Pd_total * self.DLMP_active
