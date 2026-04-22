"""Reusable Discover model card."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app import theme as t
from app.lab.services.huggingface import HFModel
from app.ui.components.primitives import Badge
from app.ui.brand_manager import BrandManager


_SKIP_TAGS = {"gguf", "region:us", "transformers", "safetensors", "text-generation"}


class ModelCard(QFrame):
    details_clicked = Signal(HFModel)
    open_hf_clicked = Signal(str)

    def __init__(self, model: HFModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._selected = False
        self.setObjectName("ModelCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(164)
        self.setMaximumHeight(196)

        root = QVBoxLayout(self)
        self._body_lay = root
        root.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        root.setSpacing(t.SPACE_3)
        self._apply_card_style()

        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(t.SPACE_5)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(7)

        self._eyebrow = QLabel("HUGGING FACE GGUF")
        self._eyebrow.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 800; letter-spacing: 1.4px;"
        )
        info.addWidget(self._eyebrow)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(t.SPACE_2)
        
        # Brand Icon
        self._brand_icon = QLabel()
        self._brand_icon.setFixedSize(24, 24)
        self._brand_icon.setPixmap(BrandManager.get_icon(model.name).pixmap(24, 24))
        name_row.addWidget(self._brand_icon)
        
        self._name = QLabel(model.name)
        self._name.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 18px; font-weight: 900;"
        )
        self._name.setWordWrap(True)
        name_row.addWidget(self._name)
        name_row.addStretch()
        info.addLayout(name_row)

        tag_row = QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.setSpacing(t.SPACE_2)
        shown = 0
        for tag in model.tags:
            if (
                tag in _SKIP_TAGS
                or tag.startswith("license:")
                or tag.startswith("dataset:")
                or tag.startswith("library:")
            ):
                continue
            tag_row.addWidget(Badge(tag))
            shown += 1
            if shown >= 3:
                break
        tag_row.addStretch()
        info.addLayout(tag_row)

        meta = QHBoxLayout()
        meta.setSpacing(t.SPACE_2)
        author = QLabel(f"by {model.author}")
        author.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px; font-weight: 600;")
        stats = QLabel(f"{model.likes:,} likes | {model.downloads:,} downloads")
        stats.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 12px;")
        meta.addWidget(author)
        meta.addWidget(stats)
        meta.addStretch()
        info.addLayout(meta)

        self._summary = QLabel("Open Settings.")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px; line-height: 1.2;")
        info.addWidget(self._summary)
        main.addLayout(info, 1)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(t.SPACE_3)
        side.setAlignment(Qt.AlignRight | Qt.AlignTop)
        if model.params_b > 0:
            side.addWidget(Badge(f"{model.params_b:.1f}B", accent=True), 0, Qt.AlignRight)
        side.addStretch()

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(t.SPACE_2)
        hf = QPushButton("Open HF")
        hf.setCursor(Qt.PointingHandCursor)
        hf.setProperty("variant", "ghost")
        hf.setProperty("size", "sm")
        hf.setStyleSheet(
            f"color: {t.ACCENT_HI}; background: transparent;"
            f" border: 1px solid {t.BORDER_LOW};"
            " padding: 5px 11px; border-radius: 8px; font-size: 11px; font-weight: 700;"
        )
        hf.clicked.connect(lambda _=False, mid=model.id: self.open_hf_clicked.emit(mid))
        actions.addWidget(hf)

        self._details_btn = QPushButton("Inspect")
        self._details_btn.setProperty("size", "sm")
        self._details_btn.setStyleSheet(
            f"background: {t.ACCENT}; color: white; font-weight: 700;"
            " padding: 5px 14px; border-radius: 8px; font-size: 11px;"
        )
        self._details_btn.clicked.connect(lambda _=False: self.details_clicked.emit(self.model))
        actions.addWidget(self._details_btn)
        side.addLayout(actions)
        main.addLayout(side)
        root.addLayout(main)

        self._fit_panel = QFrame()
        self._fit_panel.setObjectName("fit_panel")
        self._fit_panel.setFixedHeight(42)
        fit_outer = QVBoxLayout(self._fit_panel)
        fit_outer.setContentsMargins(0, 0, 0, 0)
        fit_outer.setSpacing(t.SPACE_2)
        self._fit_panel.setStyleSheet("background: transparent; border: none;")

        self._fit_rule = QFrame()
        self._fit_rule.setFixedHeight(1)
        self._fit_rule.setStyleSheet("background: #202838; border: none;")
        fit_outer.addWidget(self._fit_rule)

        fit_lay = QHBoxLayout()
        fit_lay.setContentsMargins(0, 0, 0, 0)
        fit_lay.setSpacing(t.SPACE_3)
        fit_outer.addLayout(fit_lay)

        self._fit_accent = QFrame()
        self._fit_accent.setFixedWidth(3)
        fit_lay.addWidget(self._fit_accent)

        label_col = QVBoxLayout()
        label_col.setContentsMargins(0, 0, 0, 0)
        label_col.setSpacing(0)
        self._fit_eyebrow = QLabel("BEST MATCH")
        self._fit_eyebrow.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: bold;"
        )
        self._fit_instance = QLabel("")
        self._fit_instance.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 12px; font-weight: 800;"
        )
        label_col.addWidget(self._fit_eyebrow)
        label_col.addWidget(self._fit_instance)
        fit_lay.addLayout(label_col)

        self._fit_score = QLabel("")
        self._fit_score.setMinimumWidth(48)
        self._fit_score.setAlignment(Qt.AlignCenter)
        fit_lay.addWidget(self._fit_score)

        fit_text = QVBoxLayout()
        fit_text.setContentsMargins(0, 0, 0, 0)
        fit_text.setSpacing(0)
        self._fit_label = QLabel("")
        self._fit_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self._fit_hint = QLabel("")
        self._fit_hint.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: bold;")
        fit_text.addWidget(self._fit_label)
        fit_text.addWidget(self._fit_hint)
        fit_lay.addLayout(fit_text, 1)

        self._installed_chip = QLabel("")
        self._installed_chip.setStyleSheet(
            f"color: {t.OK}; background: rgba(80,200,120,0.15);"
            "border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 700;"
        )
        self._installed_chip.hide()
        fit_lay.addWidget(self._installed_chip)

        self._install_chip = QLabel("")
        self._install_chip.setStyleSheet(
            f"color: {t.ACCENT_HI}; background: rgba(124,92,255,0.15);"
            "border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 700;"
        )
        self._install_chip.hide()
        fit_lay.addWidget(self._install_chip)

        self._fit_panel.hide()
        root.addSpacing(t.SPACE_1) # Add a bit of space before the fit panel
        root.addWidget(self._fit_panel)

    def set_selected(self, flag: bool) -> None:
        self._selected = flag
        self._apply_card_style()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.details_clicked.emit(self.model)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def is_selected(self) -> bool:
        return self._selected

    def body(self) -> QVBoxLayout:
        return self._body_lay

    def _apply_card_style(self) -> None:
        border = t.ACCENT if self._selected else "#202838"
        bg = "#111722" if self._selected else "#0f1520"
        hover_border = t.ACCENT if self._selected else "#33405a"
        shadow = "rgba(124,92,255,0.16)" if self._selected else "rgba(0,0,0,0)"
        self.setStyleSheet(
            f"""
            QFrame#ModelCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QFrame#ModelCard:hover {{
                background: #141b28;
                border-color: {hover_border};
            }}
            QFrame#ModelCard QLabel {{
                background: transparent;
            }}
            """
        )
        self.setGraphicsEffect(None)

    def set_installed_on(self, iids: list[int]) -> None:
        if iids:
            self._installed_chip.setText(f"Installed on #{iids[0]}")
            self._installed_chip.show()
            self._fit_panel.show()
        else:
            self._installed_chip.hide()

    def set_installing(self, iid: int, percent: int) -> None:
        pct = max(0, min(100, int(percent)))
        self._install_chip.setText(f"{pct}% on #{iid}")
        self._install_chip.show()
        self._fit_panel.show()

    def clear_installing(self) -> None:
        self._install_chip.hide()

    def set_scoring_pending(self) -> None:
        self._fit_panel.hide()
        self._summary.setText("Scoring hardware match...")

    def set_score_unavailable(self, message: str = "No hardware fit available.") -> None:
        self._fit_panel.hide()
        self._summary.setText(message)

    def set_detail_error(self, message: str) -> None:
        self._fit_panel.hide()
        self._summary.setText(message)

    def set_instance_scores(self, scores: list[dict] | None) -> None:
        if scores is None:
            self.set_scoring_pending()
            return

        parsed: list[dict] = []
        for item in scores:
            if isinstance(item, dict):
                parsed.append(item)
            else:
                parsed.append({"iid": str(item), "score": None, "fit": str(item), "level": "info"})

        if not parsed:
            self.set_score_unavailable()
            return

        best = max(parsed, key=lambda item: item.get("rank") or item.get("score") or 0)
        level = best.get("level", "info")
        accent = {
            "ok": t.OK,
            "info": t.INFO,
            "warn": t.WARN,
            "err": t.ERR,
        }.get(level, t.INFO)
        iid = best.get("iid", "?")
        score = best.get("score")
        fit = best.get("fit", "Fit available")
        also = [
            f"#{item.get('iid')} {item.get('score'):.0f}"
            for item in parsed
            if item is not best and item.get("score") is not None
        ]

        self._fit_instance.setText(f"Instance #{iid}")
        self._fit_score.setText("--" if score is None else f"{score:.0f}")
        self._fit_score.setStyleSheet(
            f"color: {accent}; font-size: 24px; font-weight: 900;"
        )
        self._fit_label.setText(f"{fit} ({best.get('best_quant')})" if best.get("best_quant") else fit)
        self._fit_label.setStyleSheet(
            f"color: {accent}; font-size: 12px; font-weight: bold;"
        )
        self._fit_hint.setText("Also " + " / ".join(also[:2]) if also else "")
        self._fit_accent.setStyleSheet(f"background-color: {accent}; border-radius: 2px;")
        quant = best.get("best_quant")
        if score is None:
            self._summary.setText("Scoring...")
        elif quant:
            self._summary.setText(f"Best: #{iid} · {quant}")
        else:
            self._summary.setText(f"Best: #{iid}")
        self._fit_panel.show()
