from .base_agent import BaseAgent

class DERAgent(BaseAgent):
    """
    Dağıtık Enerji Kaynağı (DER) üretici ajanı (jeneratör).
    """
    def __init__(self, agent_id, bus_id, Pmin_base=0.0, Pmax_base=0.0, Qmin_base=0.0, Qmax_base=0.0,
                 c2=0.0, c1=0.0, c0=0.0, Vmin_pu=0.90, Vmax_pu=1.05):
        super().__init__(agent_id, bus_id, Vmin_pu, Vmax_pu)
        self.Pmin_base = float(Pmin_base)
        self.Pmax_base = float(Pmax_base)
        self.Qmin_base = float(Qmin_base)
        self.Qmax_base = float(Qmax_base)
        
        # Maliyet katsayıları
        self.c2 = float(c2)
        self.c1 = float(c1)
        self.c0 = float(c0)
        
        # Ölçeklendirilmiş üretim limitleri (get_offer ile doldurulur)
        self.Pmin = 0.0
        self.Pmax = 0.0
        self.Qmin = 0.0
        self.Qmax = 0.0
        
        # Simülasyon çıktı dispatçleri
        self.Pg_dispatched = 0.0
        self.Qg_dispatched = 0.0
        self.Revenue = 0.0
        self.Cost = 0.0
        self.Profit = 0.0

    def get_offer(self, environment):
        """
        Zaman dilimi (case_time) çarpanına göre maksimum/minimum aktif ve reaktif kapasitesini ölçeklendirir.
        """
        time_mult = environment.get("time_generation_multiplier", 1.0)
        
        # Limitlerin ölçeklendirilmesi
        self.Pmin = self.Pmin_base * time_mult
        self.Pmax = self.Pmax_base * time_mult
        self.Qmin = self.Qmin_base * time_mult
        self.Qmax = self.Qmax_base * time_mult
        
        # Güvenlik bariyerleri (MATLAB'deki guards ile aynı)
        if self.Pmin > self.Pmax:
            self.Pmin = self.Pmax
        if self.Qmin > self.Qmax:
            self.Qmin = self.Qmax
            
        return {
            "bus_id": self.bus_id,
            "role": "DER",
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
        OPF sonucu atanan Pg, Qg değerlerine göre maliyet, gelir ve kâr hesabı yapar.
        """
        super().set_settlement(V_actual, theta_actual, DLMP_active, DLMP_reactive)
        self.Pg_dispatched = float(Pg_dispatched)
        self.Qg_dispatched = float(Qg_dispatched)
        
        # Gelir hesabı: Pg * DLMP_active
        self.Revenue = self.Pg_dispatched * self.DLMP_active
        
        # Üretim Maliyet hesabı (quadratic cost curve):
        # Eğer üretim yapılmıyorsa maliyet 0.0 kabul edilir
        if self.Pg_dispatched > 0.0:
            self.Cost = self.c2 * (self.Pg_dispatched ** 2) + self.c1 * self.Pg_dispatched + self.c0
        else:
            self.Cost = 0.0
            
        # Net Kâr hesabı
        self.Profit = self.Revenue - self.Cost
