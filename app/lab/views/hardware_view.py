"""Hardware monitoring view — glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QGridLayout, QLabel
from PySide6.QtCore import Qt
from app import theme as t
from app.lab.state.store import LabStore
from app.lab.views.hardware_card import HardwareCard
from app.lab.views.hardware_placeholder import HardwarePlaceholderCard


class HardwareView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.cards: dict[int, HardwareCard] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_4)

        header = QLabel("Hardware Monitoring")
        header.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: {t.FONT_SIZE_DISPLAY}px;"
            f" font-weight: 700;"
        )
        lay.addWidget(header)

        self.subtitle = QLabel("Real-time telemetry for all active remote instances.")
        self.subtitle.setProperty("role", "muted")
        lay.addWidget(self.subtitle)
        lay.addSpacing(t.SPACE_3)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, t.SPACE_3, 0)
        self.grid.setSpacing(t.SPACE_4)
        self.grid.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll)

        self.store.instance_state_updated.connect(self._on_state_updated)
        self.sync_instances()

    def sync_instances(self, *args):
        """Synchronize cards with the store's instances."""
        active_instances = self.store.all_instance_ids()

        for iid in active_instances:
            if iid not in self.cards:
                gpu_name = "GPU"
                if hasattr(self.parent(), "_controller") and self.parent()._controller:
                    inst = next(
                        (i for i in self.parent()._controller.last_instances
                         if i.id == iid), None
                    )
                    if inst:
                        gpu_name = inst.gpu_name

                card = HardwareCard(iid, gpu_name=gpu_name)
                self.cards[iid] = card
                self._arrange_cards()

        for iid, card in self.cards.items():
            state = self.store.get_state(iid)
            card.update_state(state)

        n = len(self.cards)
        self.subtitle.setText(
            f"Monitoring {n} instance{'s' if n != 1 else ''}"
            if n > 0
            else "Real-time telemetry for all active remote instances."
        )

    def _on_state_updated(self, iid: int, state):
        if iid in self.cards:
            self.cards[iid].update_state(state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_cards()

    def _arrange_cards(self):
        """Re-arrange cards into a dynamic grid, filling empty slots."""
        viewport_w = self.scroll.viewport().width() - 20
        viewport_h = self.scroll.viewport().height() - 20

        card_w_hint = 620
        cols = max(1, viewport_w // card_w_hint)

        card_h_hint = 480
        rows_to_fill = max(2, (viewport_h // card_h_hint) + 1)
        total_slots_needed = max(4, cols * rows_to_fill)

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()

        sorted_ids = sorted(self.cards.keys())
        all_items = [self.cards[iid] for iid in sorted_ids]

        while len(all_items) < total_slots_needed:
            all_items.append(HardwarePlaceholderCard())

        for idx, widget in enumerate(all_items):
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(widget, row, col)
            widget.show()

        for r in range(self.grid.rowCount()):
            self.grid.setRowStretch(r, 0)
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch(1000, 1)
