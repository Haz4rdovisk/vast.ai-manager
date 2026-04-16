"""Heuristic capacity analysis. Output strings are UX-ready (short, professional)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from app.lab.state.models import HardwareSpec


Tier = Literal["excellent", "strong", "good", "limited", "weak"]
Fit  = Literal["excellent", "good", "tight", "not_recommended"]


@dataclass
class CapacityReport:
    tier: Tier
    headline: str
    notes: list[str]


def _total_vram(hw: HardwareSpec) -> float:
    return sum(g.vram_total_gb for g in hw.gpus)


def estimate_capacity(hw: HardwareSpec) -> CapacityReport:
    vram = _total_vram(hw)
    ram = hw.ram_total_gb
    notes: list[str] = []

    if vram >= 48:
        tier: Tier = "excellent"
        headline = "Workstation-class GPU — runs any mainstream open model."
        notes.append("70B at 4-bit fits with headroom")
        notes.append("Long-context 32B comfortable")
    elif vram >= 24:
        tier = "strong"
        headline = "Excellent for 7B-14B; 32B viable with partial offload."
        notes.append("14B at 4-bit fits fully in VRAM")
        notes.append("32B at 4-bit needs partial CPU offload")
    elif vram >= 12:
        tier = "good"
        headline = "Great for 7B; 13B tight."
        notes.append("7B at 4-bit fits fully")
        notes.append("13B at 4-bit needs reduced context")
    elif vram >= 6:
        tier = "limited"
        headline = "Designed for small models up to 7B at reduced quality."
        notes.append("7B at Q4 with offload only")
        notes.append("Larger models will fall back to CPU")
    elif vram > 0:
        tier = "weak"
        headline = "Small GPU — CPU inference recommended for quality."
        notes.append("Only 3B-class or smaller fits fully on GPU")
    else:
        tier = "limited" if ram >= 32 else "weak"
        headline = "No CUDA GPU detected — CPU-only inference."
        if ram >= 64:
            notes.append("CPU can run 13B at reduced speed")
        elif ram >= 32:
            notes.append("7B at Q4 is comfortable on CPU")
        else:
            notes.append("Stick to 3B or lower for usable speed")

    if ram < 16:
        notes.append("Low system RAM — context >8k will struggle")
    if hw.disk_free_gb < 20:
        notes.append("Low free disk — GGUF files typically 4-30 GB each")

    return CapacityReport(tier=tier, headline=headline, notes=notes)


def fit_for_model(hw: HardwareSpec, approx_vram_gb: float,
                  approx_ram_gb: float) -> Fit:
    """Score a single candidate against the current hardware.
    Preference order: GPU offload -> CPU fallback. Excellent/good/tight/not."""
    vram = _total_vram(hw)
    avail_ram = hw.ram_available_gb or (hw.ram_total_gb * 0.8)

    if vram >= approx_vram_gb * 1.25:
        return "excellent"
    if vram >= approx_vram_gb * 1.05:
        return "good"
    if vram >= approx_vram_gb * 0.9:
        return "tight"

    # GPU too small — can CPU carry it?
    if avail_ram >= approx_ram_gb * 1.2:
        return "good" if hw.best_backend == "cuda" else "tight"
    if avail_ram >= approx_ram_gb:
        return "tight"
    return "not_recommended"
