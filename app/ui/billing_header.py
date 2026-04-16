from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from app import theme
from app.billing import burn_rate, autonomy_hours
from app.models import Instance, UserInfo


class BillingHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
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

        outer.addLayout(top_row)
        outer.addWidget(self.today_lbl)

    def update_values(self, user: UserInfo | None, instances: list[Instance], today_spend: float):
        if user is None:
            self.balance_lbl.setText("💰 Saldo: —")
            self.balance_lbl.setStyleSheet("")
        else:
            self.balance_lbl.setText(f"💰 Saldo: ${user.balance:.2f}")

        burn = burn_rate(instances)
        self.burn_lbl.setText(f"⚡ Gastando: ${burn:.2f}/h")

        hours = autonomy_hours(user.balance if user else 0.0, burn)
        if hours is None:
            self.autonomy_lbl.setText("⏱ Autonomia: —")
            self.autonomy_lbl.setStyleSheet("")
            if user is not None:
                self.balance_lbl.setStyleSheet("")
        else:
            self.autonomy_lbl.setText(f"⏱ Autonomia: ~{hours:.0f}h")
            color = theme.autonomy_color(hours)
            self.autonomy_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")
            self.balance_lbl.setStyleSheet(f"color: {color}; font-weight: 700;")

        self.today_lbl.setText(f"📊 Gasto hoje: ${today_spend:.2f}")
