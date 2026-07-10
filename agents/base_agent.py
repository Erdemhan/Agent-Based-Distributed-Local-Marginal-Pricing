from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """
    Tüm elektrik şebekesi düğüm ajanlarının (Load, DER, Prosumer) 
    türeyeceği temel soyut sınıf.
    """
    def __init__(self, agent_id, bus_id, Vmin_pu=0.90, Vmax_pu=1.05):
        self.id = agent_id
        self.bus_id = int(bus_id) # 1-indexed (MATLAB ve Excel ile uyumlu)
        self.Vmin_pu = float(Vmin_pu)
        self.Vmax_pu = float(Vmax_pu)
        
        # Simülasyon (OPF) sonucu doldurulacak durum öznitelikleri
        self.V_actual = 1.0       # p.u. cinsinden gerilim büyüklüğü
        self.theta_actual = 0.0   # Derece cinsinden gerilim açısı
        self.DLMP_active = 0.0    # $/MWh cinsinden aktif güç fiyatı
        self.DLMP_reactive = 0.0  # $/MVAr cinsinden reaktif güç fiyatı

    @abstractmethod
    def get_offer(self, environment):
        """
        Piyasa Operatörüne (Market Operator) sunulacak teklifi/talebi hazırlar.
        :param environment: Mevsim, günün saati gibi küresel ortam değişkenlerini içeren sözlük.
        :return: Ajanın teklif özelliklerini barındıran bir sözlük (dict).
        """
        pass

    @abstractmethod
    def set_settlement(self, V_actual, theta_actual, DLMP_active, DLMP_reactive, **kwargs):
        """
        Simülasyon sonrasında Piyasa Operatöründen gelen mutabakat sonuçlarını kaydeder
        ve ajanın kendi maliyet/kâr hesaplamalarını yapmasını sağlar.
        """
        self.V_actual = float(V_actual)
        self.theta_actual = float(theta_actual)
        self.DLMP_active = float(DLMP_active)
        self.DLMP_reactive = float(DLMP_reactive)
