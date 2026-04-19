"""Pure-Python model fit scorer for a catalog entry and remote instance."""
from __future__ import annotations

from dataclasses import dataclass

from app.lab.services.model_catalog import CatalogEntry
from app.lab.state.models import RemoteSystem


@dataclass
class ScoredModel:
    entry: CatalogEntry
    fit_level: str
    fit_label: str
    run_mode: str
    score: float
    utilization_pct: float
    memory_available_gb: float
    estimated_tps: float
    notes: list[str]


_FIT_LABEL = {
    "perfect": "Perfect fit",
    "good": "Good fit",
    "marginal": "Tight fit",
    "too_tight": "Too large",
}


class InstanceFitScorer:
    def score(self, entry: CatalogEntry, sys: RemoteSystem) -> ScoredModel:
        needed = max(entry.memory_required_gb, 0.1)
        notes: list[str] = []

        if sys.has_gpu and sys.gpu_vram_gb:
            available = float(sys.gpu_vram_gb)
            util = (needed / available) * 100
            tps = entry.estimated_tps_7b * (7.0 / max(entry.params_b, 1.0))

            if util > 100:
                fit = "too_tight"
                run_mode = "partial" if sys.ram_total_gb >= needed else "cpu"
                score = 15.0
                notes.append(
                    f"Needs {needed:.1f} GB VRAM, only {available:.1f} GB available."
                )
            elif util > 90:
                fit = "marginal"
                run_mode = "gpu"
                score = 45.0
            elif util > 70:
                fit = "good"
                run_mode = "gpu"
                score = 72.0
            else:
                fit = "perfect"
                run_mode = "gpu"
                score = 92.0
        else:
            available = float(sys.ram_total_gb)
            util = (needed / max(available, 0.1)) * 100
            run_mode = "cpu"
            tps = entry.estimated_tps_7b * (7.0 / max(entry.params_b, 1.0)) * 0.15
            notes.append("CPU inference - expect slower throughput.")

            if util > 70:
                fit = "too_tight"
                score = 20.0
            elif util > 40:
                fit = "marginal"
                score = 45.0
            else:
                fit = "good"
                score = 60.0

        return ScoredModel(
            entry=entry,
            fit_level=fit,
            fit_label=_FIT_LABEL[fit],
            run_mode=run_mode,
            score=round(score, 1),
            utilization_pct=round(util, 1),
            memory_available_gb=round(available, 2),
            estimated_tps=round(tps, 1),
            notes=notes,
        )
