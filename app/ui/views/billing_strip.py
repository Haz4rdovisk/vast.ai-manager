"""Compact always-visible billing strip. Same numbers as the old BillingHeader
(balance, burn rate, autonomy, today spend, projection) rendered on the new
design system — horizontal layout of MetricTiles + projection subtitle."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QWidget
from app import theme as t
from app.billing import (
    BurnRateTracker, autonomy_hours, format_autonomy,
    project_balance, total_burn_rate,
)
from app.models import AppConfig, Instance, UserInfo
from app.ui.components.primitives import GlassCard


class BillingStrip(GlassCard):
    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(raised=True, parent=parent)
        self._config = config or AppConfig()
        self._tracker = BurnRateTracker(
            window_size=max(1, self._config.burn_rate_smoothing_window)
        )
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._lay.setSpacing(t.SPACE_2)

        row = QHBoxLayout()
        row.setSpacing(t.SPACE_6)
        self.balance_lbl = _metric("SALDO", "—")
        self.burn_lbl    = _metric("GASTANDO", "$0.00/h")
        self.autonomy_lbl= _metric("AUTONOMIA", "—")
        self.today_lbl   = _metric("HOJE", "$0.00")
        row.addWidget(self.balance_lbl)
        row.addWidget(self.burn_lbl)
        row.addWidget(self.autonomy_lbl)
        row.addWidget(self.today_lbl)
        row.addStretch()
        self._lay.addLayout(row)

        self.projection_lbl = QLabel("")
        self.projection_lbl.setProperty("role", "muted")
        self.projection_lbl.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID};")
        self._lay.addWidget(self.projection_lbl)

    def apply_config(self, config: AppConfig) -> None:
        self._config = config
        new_window = max(1, config.burn_rate_smoothing_window)
        if new_window != self._tracker.window_size:
            self._tracker = BurnRateTracker(window_size=new_window)

    def update_values(self, user: UserInfo | None,
                      instances: list[Instance], today_spend: float) -> None:
        cfg = self._config
        if user is None:
            self.balance_lbl.set_value("—")
        else:
            self.balance_lbl.set_value(f"${user.balance:.2f}")

        burn = total_burn_rate(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        smoothed = self._tracker.update(burn)
        trend = self._tracker.get_trend()
        display_burn = smoothed if smoothed > 0 else burn
        self.burn_lbl.set_value(f"${display_burn:.2f}/h {trend.arrow}")

        hours = autonomy_hours(user.balance if user else 0.0, display_burn)
        if hours is None:
            self.autonomy_lbl.set_value("—", color=t.TEXT)
            self.projection_lbl.setText("")
        else:
            color = t.autonomy_color(hours)
            self.autonomy_lbl.set_value(format_autonomy(hours), color=color)
            self.balance_lbl.set_value(self.balance_lbl.value_text, color=color)
            if user is not None and display_burn > 0:
                p24 = project_balance(user.balance, display_burn, 24)
                p7  = project_balance(user.balance, display_burn, 24 * 7)
                p30 = project_balance(user.balance, display_burn, 24 * 30)
                self.projection_lbl.setText(
                    f"Projeção  ·  24h → ${p24['balance']:.2f}  ·  "
                    f"7d → ${p7['balance']:.2f}  ·  30d → ${p30['balance']:.2f}"
                )
            else:
                self.projection_lbl.setText("")

        self.today_lbl.set_value(f"${today_spend:.2f}")


class _metric(QWidget):
    """Private helper — small two-line metric: uppercase label + big value."""
    def __init__(self, label: str, initial: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        self._k = QLabel(label); self._k.setProperty("role", "section")
        self._v = QLabel(initial)
        self._v.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 14pt; font-weight: 700;"
        )
        v.addWidget(self._k); v.addWidget(self._v)
        self.value_text = initial

    def set_value(self, text: str, color: str | None = None):
        self.value_text = text
        self._v.setText(text)
        if color:
            self._v.setStyleSheet(
                f"color: {color}; font-size: 14pt; font-weight: 700;"
            )

    def text(self) -> str:  # shim for tests
        return self._v.text()
