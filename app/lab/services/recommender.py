"""Ranks curated catalog entries against the current hardware and optional
use-case filter. Deterministic, pure, testable."""
from __future__ import annotations
from app.lab.services.capacity import fit_for_model
from app.lab.state.models import CatalogEntry, HardwareSpec, Recommendation


_FIT_SCORE = {"excellent": 100, "good": 70, "tight": 40, "not_recommended": 0}


def _reasons(hw: HardwareSpec, e: CatalogEntry, fit: str) -> list[str]:
    vram = sum(g.vram_total_gb for g in hw.gpus)
    out: list[str] = []
    if fit == "excellent":
        out.append("Fits entirely in VRAM with headroom.")
    elif fit == "good":
        out.append("Good fit \u2014 runs smoothly on this machine.")
    elif fit == "tight":
        out.append("Will run but with limited context / slower speed.")
    else:
        out.append("Exceeds available memory \u2014 not recommended.")
    if vram and e.approx_vram_gb <= vram:
        out.append(f"Needs ~{e.approx_vram_gb:.0f} GB VRAM (you have {vram:.0f} GB).")
    elif not vram:
        out.append(f"CPU-only path: needs ~{e.approx_ram_gb:.0f} GB RAM.")
    if e.context_length >= 32768:
        out.append(f"Long context ({e.context_length:,} tokens).")
    return out


def recommend(hw: HardwareSpec, catalog: list[CatalogEntry],
              use_case: str | None = None) -> list[Recommendation]:
    items = catalog
    if use_case:
        items = [e for e in catalog if use_case in e.use_cases]
    scored: list[Recommendation] = []
    for e in items:
        fit = fit_for_model(hw, e.approx_vram_gb, e.approx_ram_gb)
        base = _FIT_SCORE[fit]
        # Reward quality, mildly penalize unused size (bigger isn't always better
        # on modest hardware).
        score = base + e.quality_tier * 10
        if fit == "not_recommended":
            score = -e.params_b   # keep them present but last
        scored.append(Recommendation(
            entry=e, fit=fit, score=score, reasons=_reasons(hw, e, fit),
        ))
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored
