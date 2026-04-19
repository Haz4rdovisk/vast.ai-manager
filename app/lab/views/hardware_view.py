"""Hardware monitoring view — glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QGridLayout, QLabel
from PySide6.QtCore import QEvent, Qt, QTimer
from app import theme as t
from app.lab.state.store import LabStore
from app.lab.views.hardware_card import HardwareCard
from app.lab.views.hardware_placeholder import HardwarePlaceholderCard


class HardwareView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.cards: dict[int, HardwareCard] = {}
        self.placeholders: list[HardwarePlaceholderCard] = []
        self._layout_signature: tuple[int, int, tuple[int, ...]] | None = None
        self._arrange_pending = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_4)
        lay.setSpacing(t.SPACE_2)

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
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, t.SPACE_2, 0)
        self.grid.setSpacing(t.SPACE_4)
        self.grid.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.container)
        self.scroll.viewport().installEventFilter(self)
        lay.addWidget(self.scroll)

        self.store.instance_state_updated.connect(self._on_state_updated)
        self.sync_instances()

    def sync_instances(self, *args):
        """Synchronize cards with the store's instances."""
        active_instances = self.store.all_instance_ids()

        for iid in list(self.cards.keys()):
            if iid not in active_instances:
                card = self.cards.pop(iid)
                card.setParent(None)
                card.deleteLater()
                self._layout_signature = None

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
                self._layout_signature = None

        for iid, card in self.cards.items():
            state = self.store.get_state(iid)
            card.update_state(state)

        n = len(self.cards)
        self.subtitle.setText(
            f"Monitoring {n} instance{'s' if n != 1 else ''}"
            if n > 0
            else "Real-time telemetry for all active remote instances."
        )
        self._schedule_arrange(force=True)

    def _on_state_updated(self, iid: int, state):
        if iid in self.cards:
            self.cards[iid].update_state(state)

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_arrange(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_arrange()

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._schedule_arrange()
        return super().eventFilter(watched, event)

    def _schedule_arrange(self, *, force: bool = False) -> None:
        if force:
            self._layout_signature = None
        if self._arrange_pending:
            return
        self._arrange_pending = True
        QTimer.singleShot(0, self._run_scheduled_arrange)

    def _run_scheduled_arrange(self) -> None:
        self._arrange_pending = False
        self._arrange_cards()

    def _available_grid_width(self) -> int:
        viewport_w = self.scroll.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.width() - (t.SPACE_5 * 2)
        return max(320, viewport_w - t.SPACE_2)

    def _columns_for_width(self, width: int) -> int:
        if width >= 1320:
            return 3
        if width >= 760:
            return 2
        return 1

    def _arrange_cards(self, *, force: bool = False):
        """Re-arrange cards into a dynamic grid, filling empty slots."""
        viewport_w = self._available_grid_width()
        viewport_h = max(320, self.scroll.viewport().height() - t.SPACE_2)

        cols = self._columns_for_width(viewport_w)
        sorted_ids = sorted(self.cards.keys())

        card_h_hint = 360
        rows_to_fill = max(2, (viewport_h // card_h_hint) + 1)
        total_slots_needed = max(cols * 2, cols * rows_to_fill, len(self.cards))
        total_slots_needed = ((total_slots_needed + cols - 1) // cols) * cols
        signature = (cols, total_slots_needed, tuple(sorted_ids))

        if not force and signature == self._layout_signature and self.grid.count():
            return
        self._layout_signature = signature

        needed_placeholders = max(0, total_slots_needed - len(sorted_ids))
        while len(self.placeholders) < needed_placeholders:
            self.placeholders.append(HardwarePlaceholderCard(self.container))
        for idx, placeholder in enumerate(self.placeholders):
            placeholder.setVisible(idx < needed_placeholders)

        all_items = [self.cards[iid] for iid in sorted_ids]
        all_items.extend(self.placeholders[:needed_placeholders])

        self.container.setUpdatesEnabled(False)
        try:
            while self.grid.count():
                self.grid.takeAt(0)

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
        finally:
            self.container.setUpdatesEnabled(True)
