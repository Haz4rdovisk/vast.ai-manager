from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Callable, Deque, Iterable
from app.models import Instance, InstanceState


# Free storage quota on Vast (approximate; cost is billed only above this).
FREE_STORAGE_GB = 50.0


class AutonomyLevel(Enum):
    """Níveis de alerta para autonomia baseada em horas restantes."""
    CRITICAL = (0.0, 1.0)      # < 1 hora - Vermelho
    LOW = (1.0, 6.0)           # 1-6 horas - Laranja
    MEDIUM = (6.0, 24.0)       # 6-24 horas - Amarelo
    GOOD = (24.0, float('inf'))  # > 24h - Verde
    
    def __init__(self, min_hours: float, max_hours: float):
        self.min_hours = min_hours
        self.max_hours = max_hours
    
    @classmethod
    def from_hours(cls, hours: float | None) -> "AutonomyLevel":
        """Determina o nível de autonomia baseado nas horas restantes."""
        if hours is None or hours < 1:
            return cls.CRITICAL
        if hours < 6:
            return cls.LOW
        if hours < 24:
            return cls.MEDIUM
        return cls.GOOD


def burn_rate(instances: Iterable[Instance]) -> float:
    """
    Calcula a taxa de consumo horário (burn rate).

    Considera instâncias em estado RUNNING e STARTING, pois ambas consomem recursos.
    """
    active_states = {InstanceState.RUNNING, InstanceState.STARTING}
    return round(sum(i.dph for i in instances if i.state in active_states), 4)


def _storage_burn_for(inst: Instance) -> float:
    """
    Storage cost for a single instance, prorated to an hourly rate.

    `Instance.storage_total_cost` on Vast is usually reported as a monthly value
    ($/month) for the allocated disk. We convert that to $/hour.  If the API
    ever returns an hourly value instead (very small, typically < $0.01), it
    still behaves reasonably — the contribution just stays tiny.

    A free storage quota (FREE_STORAGE_GB) is honored when `disk_space_gb` is
    available: if the allocation is at or below the free tier, nothing is
    charged for storage.
    """
    cost = inst.storage_total_cost
    if cost is None or cost <= 0:
        return 0.0
    if inst.disk_space_gb is not None and inst.disk_space_gb <= FREE_STORAGE_GB:
        return 0.0
    # Monthly → hourly (30 days × 24 h = 720).
    return cost / 720.0


def total_burn_rate(
    instances: Iterable[Instance],
    include_storage: bool = True,
    estimated_network_cost_per_hour: float = 0.0,
) -> float:
    """
    Burn rate completo em $/h incluindo:
      - GPU (`dph`) das instâncias em RUNNING/STARTING
      - Storage prorrateado (se `include_storage=True`)
      - Custo estimado de rede (parâmetro explícito)

    Storage é contabilizado para qualquer instância que ainda tenha disco
    alocado (inclusive STOPPED), porque Vast cobra storage mesmo com a
    instância parada — isso é exatamente o que faltava no cálculo original.
    """
    instances = list(instances)
    active_states = {InstanceState.RUNNING, InstanceState.STARTING}

    gpu = sum(i.dph for i in instances if i.state in active_states)
    storage = 0.0
    if include_storage:
        storage = sum(_storage_burn_for(i) for i in instances)
    network = max(0.0, estimated_network_cost_per_hour)

    return round(gpu + storage + network, 4)


def burn_rate_breakdown(
    instances: Iterable[Instance],
    include_storage: bool = True,
    estimated_network_cost_per_hour: float = 0.0,
) -> dict:
    """Decomposed burn rate returning GPU / storage / network $/h.

    Returns:
        {
            "gpu": float,        # compute $/h
            "storage": float,    # prorated storage $/h
            "network": float,    # estimated network $/h
            "total": float,      # sum
            "instances": [       # per-instance detail
                {"id": int, "gpu": str, "dph": float,
                 "state": str, "storage_h": float},
            ],
        }
    """
    instances = list(instances)
    active_states = {InstanceState.RUNNING, InstanceState.STARTING}

    gpu = sum(i.dph for i in instances if i.state in active_states)
    storage = sum(_storage_burn_for(i) for i in instances) if include_storage else 0.0
    network = max(0.0, estimated_network_cost_per_hour)

    per_inst = []
    for i in instances:
        per_inst.append({
            "id": i.id,
            "gpu": i.gpu_name or "GPU",
            "dph": i.dph if i.state in active_states else 0.0,
            "state": i.state.value,
            "storage_h": round(_storage_burn_for(i), 4),
        })

    return {
        "gpu": round(gpu, 4),
        "storage": round(storage, 4),
        "network": round(network, 4),
        "total": round(gpu + storage + network, 4),
        "instances": per_inst,
    }


def autonomy_hours(balance: float, burn: float) -> float | None:
    """
    Calcula as horas de autonomia restantes.
    
    Args:
        balance: Saldo atual em dólares
        burn: Taxa de consumo horário (burn rate)
        
    Returns:
        Horas de autonomia ou None se não houver consumo
    """
    if burn <= 0:
        return None
    return balance / burn


def format_autonomy(hours: float | None) -> str:
    """
    Formata horas de autonomia de forma inteligente.
    
    - < 1h: mostra minutos (ex: "~30min")
    - 1-24h: mostra horas (ex: "~5h")
    - 24h-7d: mostra dias e horas (ex: "~1d 6h", "~3d")
    - >= 7d: mostra semanas e dias (ex: "~2w 1d", "~1w")
    - None/infinito: mostra "∞"
    
    Args:
        hours: Horas de autonomia ou None
        
    Returns:
        String formatada com tempo aproximado
    """
    if hours is None or hours == float('inf'):
        return "∞"
    elif hours < 0:
        return "0min"
    elif hours < 1:
        minutes = int(round(hours * 60))
        return f"~{minutes}min"
    elif hours < 24:
        return f"~{int(round(hours))}h"
    else:
        total_days = hours / 24
        
        if total_days >= 7:
            # Use weeks for >= 7 days
            weeks = int(total_days // 7)
            remaining_days = int(round(total_days % 7))
            if remaining_days == 0:
                return f"~{weeks}w"
            return f"~{weeks}w {remaining_days}d"
        else:
            # Show days and hours for < 7 days
            days = int(total_days)
            remaining_hours = int(round((total_days - days) * 24))
            if remaining_hours == 0:
                return f"~{days}d"
            return f"~{days}d {remaining_hours}h"


@dataclass
class _Sample:
    last_duration: int
    last_dph: float


@dataclass
class DailySpendTracker:
    today_fn: Callable[[], date] = field(default_factory=lambda: date.today)
    _day: date | None = None
    _total: float = 0.0
    _per_instance: dict[int, _Sample] = field(default_factory=dict)

    def update(self, inst: Instance) -> None:
        today = self.today_fn()
        if self._day is None:
            self._day = today
        if today != self._day:
            self._day = today
            self._total = 0.0
            self._per_instance.clear()
        if inst.duration_seconds is None:
            return
        prev = self._per_instance.get(inst.id)
        if prev is None:
            self._per_instance[inst.id] = _Sample(inst.duration_seconds, inst.dph)
            return
        delta_sec = inst.duration_seconds - prev.last_duration
        if delta_sec > 0:
            self._total += (delta_sec / 3600.0) * prev.last_dph
        self._per_instance[inst.id] = _Sample(inst.duration_seconds, inst.dph)

    def today_spend(self) -> float:
        return round(self._total, 4)


class BurnRateTrend(str, Enum):
    """Tendência do burn rate ao longo do tempo."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"

    @property
    def arrow(self) -> str:
        return {
            BurnRateTrend.INCREASING: "↑",
            BurnRateTrend.DECREASING: "↓",
            BurnRateTrend.STABLE: "→",
        }[self]


@dataclass
class BurnRateTracker:
    """
    Suaviza o burn rate com média móvel e detecta tendência.

    - Mantém as últimas `window_size` amostras em uma deque.
    - `update()` insere uma nova amostra e retorna a média móvel atual.
    - `get_trend()` compara a média da metade mais recente das amostras
      contra a metade mais antiga para classificar a tendência.
    """
    window_size: int = 10
    trend_threshold: float = 0.05  # 5% de diferença conta como tendência
    history: Deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.window_size < 1:
            self.window_size = 1
        # Rebind as a bounded deque preserving any preloaded samples.
        self.history = deque(self.history, maxlen=self.window_size)

    def update(self, current_burn: float) -> float:
        """Insere amostra e devolve a média móvel atual."""
        self.history.append(float(current_burn))
        return self.average()

    def average(self) -> float:
        if not self.history:
            return 0.0
        return round(sum(self.history) / len(self.history), 4)

    def get_trend(self) -> BurnRateTrend:
        """
        Classifica a tendência comparando a metade recente contra a antiga.

        Precisa de ao menos 4 amostras para ser confiável; abaixo disso
        reporta STABLE.
        """
        n = len(self.history)
        if n < 4:
            return BurnRateTrend.STABLE
        half = n // 2
        samples = list(self.history)
        old_avg = sum(samples[:half]) / half
        new_avg = sum(samples[-half:]) / half
        if old_avg <= 0:
            # Saímos de "sem consumo" para "com consumo" → subindo.
            return BurnRateTrend.INCREASING if new_avg > 0 else BurnRateTrend.STABLE
        delta = (new_avg - old_avg) / old_avg
        if delta > self.trend_threshold:
            return BurnRateTrend.INCREASING
        if delta < -self.trend_threshold:
            return BurnRateTrend.DECREASING
        return BurnRateTrend.STABLE

    def reset(self) -> None:
        self.history.clear()


def project_balance(
    balance: float,
    burn: float,
    hours_ahead: float,
    include_trend_factor: bool = False,
    trend: BurnRateTrend | None = None,
    trend_multiplier: float = 0.10,
) -> dict:
    """
    Projeta o saldo após `hours_ahead` horas.

    Quando `include_trend_factor=True` e uma `trend` é fornecida, o burn é
    ajustado em ±`trend_multiplier` (10% por padrão) para refletir uma
    tendência de alta/baixa do consumo.

    Returns:
        {
            "balance": saldo projetado (pode ser negativo),
            "autonomy_hours": horas restantes no novo burn (ou None),
            "burn_used": burn efetivamente aplicado na projeção,
        }
    """
    effective_burn = max(0.0, burn)
    if include_trend_factor and trend is not None:
        if trend is BurnRateTrend.INCREASING:
            effective_burn *= (1.0 + trend_multiplier)
        elif trend is BurnRateTrend.DECREASING:
            effective_burn *= max(0.0, 1.0 - trend_multiplier)

    projected = balance - effective_burn * max(0.0, hours_ahead)
    remaining = autonomy_hours(max(0.0, projected), effective_burn)

    return {
        "balance": round(projected, 4),
        "autonomy_hours": remaining,
        "burn_used": round(effective_burn, 4),
    }
