from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget

from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.services.instance_filter import FilterState, apply, gpu_key
from app.theme import FONT_DISPLAY, TEXT_HI
from app.ui.components import icons
from app.ui.components.primitives import GlassCard, IconButton, SkeletonBlock
from app.ui.views.instances.bulk_action_bar import BulkActionBar
from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
from app.ui.views.instances.filter_bar import FilterBar
from app.ui.views.instances.instance_card import InstanceCard
from app.ui.views.instances.label_tabs import LabelTabs
from app.ui.views.instances.log_modal import LogModal
from app.ui.views.instances.action_bar import SCHEDULING_TOOLTIP


class InstancesView(QWidget):
    """Composer for header, filters, label tabs, cards, and bulk bar."""

    activate_requested = Signal(int)
    deactivate_requested = Signal(int)
    connect_requested = Signal(int)
    disconnect_requested = Signal(int)
    destroy_requested = Signal(int)
    set_label_requested = Signal(int, str)
    open_lab_requested = Signal(int)
    open_settings_requested = Signal()
    open_logs_requested = Signal()
    open_analytics_requested = Signal()
    bulk_requested = Signal(str, list, dict)
    fix_ssh_requested = Signal(int)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._all: list[Instance] = []
        self._cards: dict[int, InstanceCard] = {}
        self._selected: set[int] = set()
        self._loading_cards: list[GlassCard] = []
        self._start_requested_ids: set[int] = {
            int(iid)
            for iid in getattr(controller.config, "start_requested_ids", []) or []
        }
        now = time.time()
        saved_requested_at = getattr(controller.config, "start_requested_at", {}) or {}
        self._start_requested_at: dict[int, float] = {
            int(iid): float(
                saved_requested_at.get(iid, saved_requested_at.get(str(iid), now))
            )
            for iid in self._start_requested_ids
        }
        self._select_mode = False
        self._log_history: list[str] = []
        self._tunnels: dict[int, TunnelStatus] = {}
        self._filter = FilterState.from_dict(controller.config.instance_filters)
        self._build()
        self.set_loading()

        controller.log_line.connect(self._on_log_line)
        controller.tunnel_status_changed.connect(self._on_tunnel_status)
        controller.live_metrics.connect(self._on_live_metrics)
        controller.action_done.connect(self._on_action_done)
        if hasattr(controller, "bulk_done"):
            controller.bulk_done.connect(self._on_bulk_done)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("My Instances (0)")
        font = self.title.font()
        font.setPointSize(14)
        font.setBold(True)
        font.setFamily(FONT_DISPLAY)
        self.title.setFont(font)
        self.title.setStyleSheet(f"color: {TEXT_HI};")
        head.addWidget(self.title)
        head.addStretch(1)

        self.btn_select = IconButton(icons.SELECT, "Select instances")
        self.btn_select.clicked.connect(self._toggle_select_mode)
        head.addWidget(self.btn_select)

        self.btn_logs = IconButton(icons.LOG, "Open global logs")
        self.btn_logs.clicked.connect(self.open_logs_requested)
        head.addWidget(self.btn_logs)

        self.btn_settings = IconButton(icons.SETTINGS, "Settings")
        self.btn_settings.clicked.connect(self.open_settings_requested)
        head.addWidget(self.btn_settings)

        self.btn_start_all = QPushButton("Start All")
        self.btn_start_all.clicked.connect(lambda: self._bulk_from_visible("start"))
        head.addWidget(self.btn_start_all)
        outer.addLayout(head)

        self.filter_bar = FilterBar(self._filter)
        self.filter_bar.changed.connect(self._on_filter_changed)
        outer.addWidget(self.filter_bar)

        self.label_tabs = LabelTabs()
        self.label_tabs.label_selected.connect(self._on_label_tab)
        outer.addWidget(self.label_tabs)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self._cards_layout = QVBoxLayout(host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch(1)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll, stretch=1)

        self.bulk_bar = BulkActionBar()
        self.bulk_bar.action_clicked.connect(self._on_bulk_action)
        self.bulk_bar.clear_clicked.connect(self._clear_selection)
        self.bulk_bar.setVisible(False)
        outer.addWidget(self.bulk_bar)

    def handle_refresh(self, instances: list[Instance], user: UserInfo) -> None:
        self._clear_loading()
        self._all = self._with_sticky_scheduling(list(instances))
        self.title.setText(f"My Instances ({len(self._all)})")

        gpus = sorted({gpu_key(inst) for inst in self._all})
        self.filter_bar.set_gpu_options(gpus)
        labels = sorted({inst.label for inst in self._all if inst.label})
        self.filter_bar.set_label_options(labels)

        counts: dict[str, int] = {"": len(self._all)}
        none_count = sum(1 for inst in self._all if not inst.label)
        if none_count:
            counts["__none__"] = none_count
        for label in labels:
            counts[label] = sum(1 for inst in self._all if inst.label == label)
        self.label_tabs.update_labels(counts)

        alive = {inst.id for inst in self._all}
        self._selected &= alive
        self._reapply_filter()

    def set_loading(self) -> None:
        if self._all or self._cards or self._loading_cards:
            return
        self.title.setText("My Instances")
        for _ in range(3):
            card = GlassCard()
            body = card.body()
            body.setContentsMargins(14, 14, 14, 14)
            body.setSpacing(10)
            body.addWidget(SkeletonBlock(260, 20))
            body.addWidget(SkeletonBlock(520, 14))
            body.addWidget(SkeletonBlock(680, 14))
            body.addWidget(SkeletonBlock(420, 14))
            body.addWidget(SkeletonBlock(300, 24))
            self._loading_cards.append(card)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _clear_loading(self) -> None:
        while self._loading_cards:
            widget = self._loading_cards.pop()
            widget.setParent(None)
            widget.deleteLater()

    def _on_filter_changed(self, state: FilterState) -> None:
        self._filter = state
        self._controller.update_instance_filters(state.to_dict())
        self._reapply_filter()

    def _on_label_tab(self, key: str) -> None:
        self._filter.label = key or None
        self.filter_bar.state.label = self._filter.label
        self._controller.update_instance_filters(self._filter.to_dict())
        self._reapply_filter()

    def _reapply_filter(self) -> None:
        filtered = apply(self._all, self._filter)
        seen: set[int] = set()
        for inst in filtered:
            if inst.id in self._cards:
                self._cards[inst.id].update_instance(
                    inst, self._tunnels.get(inst.id, TunnelStatus.DISCONNECTED)
                )
            else:
                card = self._build_card(inst)
                self._cards[inst.id] = card
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            seen.add(inst.id)

        for iid in list(self._cards):
            if iid not in seen:
                widget = self._cards.pop(iid)
                widget.setParent(None)
                widget.deleteLater()
        self._refresh_bulk_bar()

    def _build_card(self, inst: Instance) -> InstanceCard:
        port = self._controller.port_allocator.get(inst.id)
        card = InstanceCard(
            inst,
            port=port,
            tunnel=self._tunnels.get(inst.id, TunnelStatus.DISCONNECTED),
            selected=inst.id in self._selected,
            select_mode=self._select_mode,
        )
        card.activate_requested.connect(self._on_activate_requested)
        card.deactivate_requested.connect(self.deactivate_requested)
        card.connect_requested.connect(self.connect_requested)
        card.disconnect_requested.connect(self.disconnect_requested)
        card.destroy_requested.connect(self._confirm_single_destroy)
        card.lab_requested.connect(self.open_lab_requested)
        card.fix_ssh_requested.connect(self.fix_ssh_requested)
        card.log_requested.connect(self._open_log_modal)
        card.label_requested.connect(self._prompt_label)
        card.selection_toggled.connect(self._on_selection_toggled)
        return card

    def _toggle_select_mode(self) -> None:
        self._select_mode = not self._select_mode
        for card in self._cards.values():
            card.set_select_mode(self._select_mode)
        if not self._select_mode:
            self._clear_selection()
        else:
            self._refresh_bulk_bar()

    def _on_selection_toggled(self, iid: int, on: bool) -> None:
        if on:
            self._selected.add(iid)
        else:
            self._selected.discard(iid)
        self._refresh_bulk_bar()

    def _clear_selection(self) -> None:
        self._selected.clear()
        for card in self._cards.values():
            card.set_selected(False)
        self._refresh_bulk_bar()

    def _refresh_bulk_bar(self) -> None:
        self.bulk_bar.setVisible(self._select_mode or bool(self._selected))
        self.bulk_bar.set_count(len(self._selected))

    def _on_bulk_action(self, action: str) -> None:
        ids = sorted(self._selected) if self._selected else [
            inst.id for inst in apply(self._all, self._filter)
        ]
        if not ids:
            return
        id_set = set(ids)
        instances = [inst for inst in self._all if inst.id in id_set]
        dialog = ConfirmBulkDialog(action, instances, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            if action == "start":
                self._mark_start_requested(ids)
            self.bulk_requested.emit(action, ids, dialog.collect_opts())
            if not self._select_mode:
                self._clear_selection()

    def _bulk_from_visible(self, action: str) -> None:
        ids = [inst.id for inst in apply(self._all, self._filter)]
        if not ids:
            return
        id_set = set(ids)
        instances = [inst for inst in self._all if inst.id in id_set]
        dialog = ConfirmBulkDialog(action, instances, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            if action == "start":
                self._mark_start_requested(ids)
            self.bulk_requested.emit(action, ids, dialog.collect_opts())

    def _confirm_single_destroy(self, iid: int) -> None:
        instances = [inst for inst in self._all if inst.id == iid]
        dialog = ConfirmBulkDialog("destroy", instances, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.bulk_requested.emit("destroy", [iid], dialog.collect_opts())

    def _prompt_label(self, iid: int) -> None:
        from PySide6.QtWidgets import QInputDialog

        inst = next((item for item in self._all if item.id == iid), None)
        current = (inst.label if inst else "") or ""
        text, ok = QInputDialog.getText(self, "Label", f"Label for #{iid}:", text=current)
        if ok:
            self.set_label_requested.emit(iid, text)

    def _on_activate_requested(self, iid: int) -> None:
        self._mark_start_requested([iid])
        self.activate_requested.emit(iid)

    def _with_sticky_scheduling(self, instances: list[Instance]) -> list[Instance]:
        before = set(self._start_requested_ids)
        before_at = dict(self._start_requested_at)
        alive = {inst.id for inst in instances}
        self._start_requested_ids &= alive
        self._start_requested_at = {
            iid: ts for iid, ts in self._start_requested_at.items() if iid in alive
        }
        out: list[Instance] = []
        for inst in instances:
            if inst.id in self._start_requested_ids:
                if inst.state == InstanceState.RUNNING:
                    self._start_requested_ids.discard(inst.id)
                    self._start_requested_at.pop(inst.id, None)
                    out.append(inst)
                else:
                    out.append(self._as_scheduling(inst))
            else:
                out.append(inst)
        if self._start_requested_ids != before or self._start_requested_at != before_at:
            self._persist_start_requested_ids()
        return out

    def _mark_start_requested(self, ids: list[int]) -> None:
        id_set = set(ids)
        before = set(self._start_requested_ids)
        before_at = dict(self._start_requested_at)
        now = time.time()
        self._start_requested_ids.update(id_set)
        for iid in id_set:
            self._start_requested_at.setdefault(iid, now)
        if self._start_requested_ids != before or self._start_requested_at != before_at:
            self._persist_start_requested_ids()
        updated: list[Instance] = []
        changed: dict[int, Instance] = {}
        for inst in self._all:
            if inst.id in id_set and inst.state != InstanceState.RUNNING:
                next_inst = self._as_scheduling(inst)
                updated.append(next_inst)
                changed[inst.id] = next_inst
            else:
                updated.append(inst)
        self._all = updated
        for iid, inst in changed.items():
            card = self._cards.get(iid)
            if card is not None:
                card.update_instance(
                    inst, self._tunnels.get(iid, TunnelStatus.DISCONNECTED)
                )

    def _as_scheduling(self, inst: Instance) -> Instance:
        raw = dict(inst.raw)
        raw["actual_status"] = "scheduling"
        raw["intended_status"] = "running"
        raw["_is_scheduling"] = True
        return replace(
            inst,
            state=InstanceState.STARTING,
            status_message=inst.status_message or SCHEDULING_TOOLTIP,
            raw=raw,
        )

    def _clear_start_requested(self, ids: list[int]) -> None:
        before = set(self._start_requested_ids)
        before_at = dict(self._start_requested_at)
        for iid in ids:
            self._start_requested_ids.discard(iid)
            self._start_requested_at.pop(iid, None)
        if self._start_requested_ids != before or self._start_requested_at != before_at:
            self._persist_start_requested_ids()

    def _persist_start_requested_ids(self) -> None:
        updater = getattr(self._controller, "update_start_requested_ids", None)
        if callable(updater):
            updater(sorted(self._start_requested_ids), dict(self._start_requested_at))

    def _on_action_done(self, iid: int, action: str, ok: bool, _msg: str) -> None:
        if action == "start" and not ok:
            self._clear_start_requested([iid])
        elif action in ("stop", "destroy"):
            self._clear_start_requested([iid])

    def _on_bulk_done(self, action: str, ok: list, fail: list) -> None:
        if action == "start":
            self._clear_start_requested(fail)
        elif action in ("stop", "destroy"):
            self._clear_start_requested(ok + fail)

    def _on_log_line(self, line: str) -> None:
        self._log_history.append(line)
        if len(self._log_history) > 2000:
            self._log_history = self._log_history[-2000:]

    def _open_log_modal(self, iid: int) -> None:
        modal = LogModal(iid, self._log_history, parent=self)
        modal.exec()

    def _on_tunnel_status(self, iid: int, status: str, _msg: str) -> None:
        try:
            self._tunnels[iid] = TunnelStatus(status)
        except ValueError:
            return
        if iid in self._cards:
            self._cards[iid].update_instance(self._cards[iid].inst, self._tunnels[iid])

    def _on_live_metrics(self, iid: int, metrics: dict) -> None:
        if iid in self._cards:
            self._cards[iid].apply_metrics(metrics)
