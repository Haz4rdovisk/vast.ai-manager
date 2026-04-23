from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models_rental import Offer


HOURS_PER_BILLING_MONTH = 30.0 * 24.0


@dataclass(frozen=True)
class OfferPriceBreakdown:
    compute_hour: float
    storage_hour: float
    total_hour: float
    storage_gib: float
    storage_per_gb_month: float | None
    inet_up_per_gb: float | None
    inet_down_per_gb: float | None

    @property
    def compute_day(self) -> float:
        return self.compute_hour * 24.0

    @property
    def storage_day(self) -> float:
        return self.storage_hour * 24.0

    @property
    def total_day(self) -> float:
        return self.total_hour * 24.0

    @property
    def compute_month(self) -> float:
        return self.compute_hour * HOURS_PER_BILLING_MONTH

    @property
    def storage_month(self) -> float:
        return self.storage_hour * HOURS_PER_BILLING_MONTH

    @property
    def total_month(self) -> float:
        return self.total_hour * HOURS_PER_BILLING_MONTH


def raw_float(raw: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = raw.get(name)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def requested_storage_gib(offer: Offer) -> float:
    """Storage selected for the rental search, not host disk capacity."""
    value = raw_float(
        offer.raw,
        "_requested_storage_gib",
        "allocated_storage",
        "allocated_storage_gb",
        "allocated_storage_gib",
        "disk_gb",
    )
    return max(value or 0.0, 0.0)


def offer_price_breakdown(offer: Offer) -> OfferPriceBreakdown:
    total_hour = max(float(offer.effective_price() or 0.0), 0.0)
    storage_gib = requested_storage_gib(offer)
    storage_per_gb_month = offer.storage_cost
    storage_hour = 0.0
    if storage_gib > 0 and storage_per_gb_month is not None:
        storage_hour = max(float(storage_per_gb_month), 0.0) * storage_gib / HOURS_PER_BILLING_MONTH

    # Vast search receives allocated_storage and returns dph_total as the base
    # hourly rental price for that allocation. If storage is not part of the
    # returned price for an unusual row, don't let the breakdown exceed total.
    included_storage_hour = min(storage_hour, total_hour)
    compute_hour = max(total_hour - included_storage_hour, 0.0)

    return OfferPriceBreakdown(
        compute_hour=compute_hour,
        storage_hour=included_storage_hour,
        total_hour=total_hour,
        storage_gib=storage_gib,
        storage_per_gb_month=storage_per_gb_month,
        inet_up_per_gb=raw_float(offer.raw, "inet_up_cost"),
        inet_down_per_gb=raw_float(offer.raw, "inet_down_cost"),
    )
