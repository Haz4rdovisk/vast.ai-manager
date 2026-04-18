"""Compact billing bar — shows balance + burn rate inline.
All detailed cost analysis lives in AnalyticsView."""
from __future__ import annotations
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
from PySide6.QtCore import Signal
from app import theme as t
from app.billing import BurnRateTracker, autonomy_hours, format_autonomy, total_burn_rate
from app.models import AppConfig, Instance, UserInfo
from app.ui.components.primitives import GlassCard, VDivider


class BillingStrip(GlassCard):
    """Compact inline bar: Balance | Burn Rate | Autonomy — one row."""
    analytics_requested = Signal()

    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(raised=True, parent=parent)
        self._config = config or AppConfig()
        self._tracker = BurnRateTracker(
            window_size=max(1, self._config.burn_rate_smoothing_window)
        )
        self._lay.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_3)
        self._lay.setSpacing(0)

        row = QHBoxLayout()
        row.setSpacing(t.SPACE_5)

        # Balance
        self.bal_lbl = QLabel("$—")
        self.bal_lbl.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 18px; font-weight: 700;"
            f" font-family: {t.FONT_MONO};"
        )
        row.addWidget(self.bal_lbl)

        row.addWidget(VDivider())

        # Burn rate
        self.burn_lbl = QLabel("$0.00/h")
        self.burn_lbl.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: 13px; font-weight: 600;"
            f" font-family: {t.FONT_MONO};"
        )
        row.addWidget(self.burn_lbl)

        row.addWidget(VDivider())

        # Autonomy
        self.auto_lbl = QLabel("\u2014")
        self.auto_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: 13px; font-weight: 600;"
        )
        row.addWidget(self.auto_lbl)

        row.addStretch()

        # Link to Analytics
        self.analytics_btn = QPushButton("Analytics \u2192")
        self.analytics_btn.setProperty("variant", "ghost")
        self.analytics_btn.setFixedHeight(30)
        self.analytics_btn.clicked.connect(self.analytics_requested.emit)
        row.addWidget(self.analytics_btn)

        self._lay.addLayout(row)

    def apply_config(self, config: AppConfig):
        self._config = config
        new_window = max(1, config.burn_rate_smoothing_window)
        if new_window != self._tracker.window_size:
            self._tracker = BurnRateTracker(window_size=new_window)

    def update_values(self, user: UserInfo | None,
                      instances: list[Instance], today_spend: float):
        cfg = self._config
        if user is None:
            self.bal_lbl.setText("$\u2014")
        else:
            self.bal_lbl.setText(f"${user.balance:.2f}")

        burn = total_burn_rate(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        smoothed = self._tracker.update(burn)
        trend = self._tracker.get_trend()
        display_burn = smoothed if smoothed > 0 else burn
        self.burn_lbl.setText(f"${display_burn:.2f}/h {trend.arrow}")

        hours = autonomy_hours(user.balance if user else 0.0, display_burn)
        if hours is None:
            self.auto_lbl.setText("— remaining")
            self.auto_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 13px; font-weight: 600;")
        else:
            color = t.autonomy_color(hours)
            self.auto_lbl.setText(f"{format_autonomy(hours)} remaining")
            self.auto_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;")
            self.bal_lbl.setStyleSheet(
                f"color: {color}; font-size: 18px; font-weight: 700;"
                f" font-family: {t.FONT_MONO};"
            )
