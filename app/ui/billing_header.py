from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from app import theme
from app.billing import (
    BurnRateTracker,
    BurnRateTrend,
    autonomy_hours,
    format_autonomy,
    project_balance,
    total_burn_rate,
)
from app.models import AppConfig, Instance, UserInfo


class BillingHeader(QFrame):
    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._config = config or AppConfig()
        self._tracker = BurnRateTracker(
            window_size=max(1, self._config.burn_rate_smoothing_window)
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(28)
        self.balance_lbl = QLabel("💰 Saldo: —")
        self.balance_lbl.setObjectName("h2")
        self.burn_lbl = QLabel("⚡ Gastando: $0.00/h")
        self.burn_lbl.setObjectName("h2")
        self.autonomy_lbl = QLabel("⏱ Autonomia: —")
        self.autonomy_lbl.setObjectName("h2")
        top_row.addWidget(self.balance_lbl)
        top_row.addWidget(self.burn_lbl)
        top_row.addWidget(self.autonomy_lbl)
        top_row.addStretch()

        self.today_lbl = QLabel("📊 Gasto hoje: $0.00")
        self.today_lbl.setObjectName("secondary")
        self.projection_lbl = QLabel("")
        self.projection_lbl.setObjectName("secondary")

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(24)
        bottom_row.addWidget(self.today_lbl)
        bottom_row.addWidget(self.projection_lbl)
        bottom_row.addStretch()

        outer.addLayout(top_row)
        outer.addLayout(bottom_row)

    # ------------------------------------------------------------------ #
    def apply_config(self, config: AppConfig) -> None:
        """Re-aplica configurações que afetam o cálculo (janela, storage, rede)."""
        self._config = config
        new_window = max(1, config.burn_rate_smoothing_window)
        if new_window != self._tracker.window_size:
            self._tracker = BurnRateTracker(window_size=new_window)

    # ------------------------------------------------------------------ #
    def update_values(
        self,
        user: UserInfo | None,
        instances: list[Instance],
        today_spend: float,
    ) -> None:
        cfg = self._config

        if user is None:
            self.balance_lbl.setText("💰 Saldo: —")
            self.balance_lbl.setStyleSheet("")
        else:
            self.balance_lbl.setText(f"💰 Saldo: ${user.balance:.2f}")

        # Burn rate completo (GPU + storage + rede estimada).
        burn = total_burn_rate(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        smoothed = self._tracker.update(burn)
        trend = self._tracker.get_trend()

        # A média móvel é o que deve guiar a exibição de autonomia — evita
        # pulos bruscos quando o Vast publica um dph momentaneamente ruidoso.
        display_burn = smoothed if smoothed > 0 else burn
        self.burn_lbl.setText(
            f"⚡ Gastando: ${display_burn:.2f}/h {trend.arrow}"
        )

        hours = autonomy_hours(user.balance if user else 0.0, display_burn)
        if hours is None:
            self.autonomy_lbl.setText("⏱ Autonomia: —")
            self.autonomy_lbl.setStyleSheet("")
            if user is not None:
                self.balance_lbl.setStyleSheet("")
            self.projection_lbl.setText("")
        else:
            formatted = format_autonomy(hours)
            self.autonomy_lbl.setText(f"⏱ Autonomia: {formatted}")
            color = theme.autonomy_color(hours)
            self.autonomy_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")
            self.balance_lbl.setStyleSheet(f"color: {color}; font-weight: 700;")

            # Projeções 24h / 7d, apenas quando faz sentido.
            if user is not None and display_burn > 0:
                p24 = project_balance(user.balance, display_burn, 24)
                p7d = project_balance(user.balance, display_burn, 24 * 7)
                self.projection_lbl.setText(
                    f"🔮 Projeção: 24h → ${p24['balance']:.2f}  ·  "
                    f"7d → ${p7d['balance']:.2f}"
                )
            else:
                self.projection_lbl.setText("")

        self.today_lbl.setText(f"📊 Gasto hoje: ${today_spend:.2f}")

        # Tooltip rico para quem quiser os números separados.
        gpu_only = sum(
            i.dph for i in instances
            if i.state.value in ("running", "starting")
        )
        storage_only = display_burn - gpu_only - cfg.estimated_network_cost_per_hour
        storage_only = max(0.0, storage_only)
        self.burn_lbl.setToolTip(
            f"GPU: ${gpu_only:.2f}/h\n"
            f"Storage: ${storage_only:.2f}/h\n"
            f"Rede (estimada): ${cfg.estimated_network_cost_per_hour:.2f}/h\n"
            f"Tendência: {trend.value}"
        )
