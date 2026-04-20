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
    "pending": "Analyzing...",
}


class InstanceFitScorer:
    def score(self, entry: CatalogEntry, sys: RemoteSystem) -> ScoredModel:
        needed = max(entry.memory_required_gb, 0.1)
        notes: list[str] = []

        # GUARD: If system hasn't been probed (missing basic RAM/GPU info)
        if sys.ram_total_gb == 0 and not sys.has_gpu:
            return ScoredModel(
                entry=entry,
                fit_level="pending",
                fit_label="Analyzing...",
                run_mode="none",
                score=0.0,
                utilization_pct=0.0,
                memory_available_gb=0.0,
                estimated_tps=0.0,
                notes=["No hardware data available for this instance. Connect via SSH to probe."],
            )

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
                score = 55.0  # Increased from 45
            elif util > 70:
                fit = "good"
                run_mode = "gpu"
                score = 80.0  # Increased from 72
            else:
                fit = "perfect"
                run_mode = "gpu"
                # Dynamic score: 100 base, minus a small penalty for utilization
                score = 100.0 - (util / 5.0) 
        else:
            available = float(sys.ram_total_gb)
            util = (needed / max(available, 0.1)) * 100
            run_mode = "cpu"
            tps = entry.estimated_tps_7b * (7.0 / max(entry.params_b, 1.0)) * 0.15
            notes.append("CPU inference - expect slower throughput.")

            if util > 70:
                fit = "too_tight"
                score = 15.0
            elif util > 40:
                fit = "marginal"
                score = 40.0
            else:
                fit = "good"
                score = 70.0  # increased from 60

        return ScoredModel(
            entry=entry,
            fit_level=fit,
            fit_label=_FIT_LABEL.get(fit, "Unknown"),
            run_mode=run_mode,
            score=round(max(0, score), 1),
            utilization_pct=round(util, 1),
            memory_available_gb=round(available, 2),
            estimated_tps=round(tps, 1),
            notes=notes,
        )
