"""Hardware monitoring view with responsive 2-column grid layout."""
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
        header.setProperty("role", "display")
        lay.addWidget(header)
        
        msg = QLabel("Real-time telemetry for all active remote instances.")
        msg.setProperty("role", "muted")
        lay.addWidget(msg)
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
        
        # Connect to store for LIVE updates
        self.store.instance_state_updated.connect(self._on_state_updated)
        
        # Initial sync
        self.sync_instances()

    def sync_instances(self):
        """Synchronize cards with the store's instances."""
        active_instances = self.store.all_instance_ids()
        
        # Add missing cards
        for iid in active_instances:
            if iid not in self.cards:
                # Find instance name from controller cache if possible
                gpu_name = "GPU"
                if hasattr(self.parent(), "_controller") and self.parent()._controller:
                    inst = next((i for i in self.parent()._controller.last_instances if i.id == iid), None)
                    if inst: gpu_name = inst.gpu_name
                
                card = HardwareCard(iid, gpu_name=gpu_name)
                self.cards[iid] = card
                self._arrange_cards()

        # Update all cards
        for iid, card in self.cards.items():
            state = self.store.get_state(iid)
            card.update_state(state)

    def _on_state_updated(self, iid: int, state):
        """Update a specific card when its state changes."""
        if iid in self.cards:
            self.cards[iid].update_state(state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_cards()

    def _arrange_cards(self):
        """Re-arrange cards into a dynamic grid, filling EVERY empty visible slot."""
        # Calculate viewport dimensions
        viewport_w = self.scroll.viewport().width() - 20
        viewport_h = self.scroll.viewport().height() - 20
        
        # Determine cols based on card size
        card_w_hint = 650
        cols = max(1, viewport_w // card_w_hint)
        
        # Determine how many rows are needed to fill the view height
        card_h_hint = 480
        rows_to_fill = max(2, (viewport_h // card_h_hint) + 1)
        total_slots_needed = max(4, cols * rows_to_fill)
        
        # Clear existing layout
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
            
        sorted_ids = sorted(self.cards.keys())
        all_items = [self.cards[iid] for iid in sorted_ids]
        
        # Fill ALL remaining slots with placeholders so there is ZERO black space
        while len(all_items) < total_slots_needed:
            all_items.append(HardwarePlaceholderCard())
            
        for idx, widget in enumerate(all_items):
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(widget, row, col)
            widget.show()

        # Reset stretches
        for r in range(self.grid.rowCount()):
            self.grid.setRowStretch(r, 0)
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
            
        # Give active columns equal stretch (100% split)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
            
        # Soak up remaining vertical space at the bottom
        self.grid.setRowStretch(1000, 1)
