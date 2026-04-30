"""Reusable Discover model card."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.lab.services.huggingface import HFModel, HFModelFile, estimate_gguf_size_gb
from app.ui.brand_manager import BrandManager


_CODING_RX = re.compile(
    r"\b(coder?|starcoder\d*|deepseek[-_]?coder|qwen[-_]?coder|wizardcoder|codellama|codegemma)\b",
    re.I,
)
_REASONING_RX = re.compile(r"\b(r1|qwq|reasoner?|o1|phi[-_]?reason|deepseek[-_]?r)\b", re.I)
_CHAT_RX = re.compile(r"\b(chat|instruct|sft|assistant|rp|roleplay)\b", re.I)


class ElidedLabel(QLabel):
    """QLabel that reports 0 minimum width and elides its text with '…'."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text
        self._apply_elide(self.width())

    def text(self) -> str:  # type: ignore[override]
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide(event.size().width())

    def _apply_elide(self, width: int) -> None:
        if width <= 0:
            super().setText(self._full_text)
            return
        elided = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width)
        super().setText(elided)

    def minimumSizeHint(self) -> QSize:
        h = super().minimumSizeHint().height()
        return QSize(0, h)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full_text), fm.height())


class _MetaStat(QWidget):
    def __init__(self, emoji: str, label: str, value: str, *, accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("model-card-meta-stat")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet("QWidget#model-card-meta-stat { background: transparent; border: none; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)

        self._emoji = QLabel(emoji)
        self._emoji.setFixedWidth(18)
        self._emoji.setAlignment(Qt.AlignCenter)
        self._emoji.setStyleSheet("font-size: 15px;")
        lay.addWidget(self._emoji, 0, Qt.AlignVCenter)

        eyebrow = QLabel(label.upper())
        eyebrow.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 9px; font-weight: 800; letter-spacing: 1px;"
        )
        lay.addWidget(eyebrow, 0, Qt.AlignVCenter)

        self._value = ElidedLabel(value)
        self._value.setStyleSheet(
            f"color: {t.ACCENT_SOFT if accent else t.TEXT_HI}; font-size: 13px; font-weight: 800;"
        )
        self._value.setToolTip(value)
        lay.addWidget(self._value, 0, Qt.AlignVCenter)
        lay.addStretch(1)

    def value_label(self) -> ElidedLabel:
        return self._value


class _InfoRow(QWidget):
    def __init__(self, key: str, value: str = "", *, accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("model-card-info-row")
        self.setStyleSheet(
            f"""
            QWidget#model-card-info-row {{
                background: transparent;
                border-bottom: 1px solid rgba(255,255,255,0.07);
            }}
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(10)

        self._key = QLabel(key)
        self._key.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: 12px; font-weight: 600;"
        )
        lay.addWidget(self._key, 0, Qt.AlignVCenter)

        lay.addStretch(1)

        self._value_pill = QFrame()
        self._value_pill.setObjectName("model-card-value-pill")
        self._value_pill.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._value_pill.setStyleSheet(
            f"""
            QFrame#model-card-value-pill {{
                background: {"rgba(124,92,255,0.12)" if accent else "#151D2A"};
                border: 1px solid {"rgba(124,92,255,0.28)" if accent else "rgba(255,255,255,0.06)"};
                border-radius: 7px;
            }}
            """
        )
        pill_lay = QHBoxLayout(self._value_pill)
        pill_lay.setContentsMargins(8, 3, 8, 3)
        pill_lay.setSpacing(0)

        self._value = ElidedLabel(value)
        self._value.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._value.setStyleSheet(
            f"""
            color: {t.ACCENT_SOFT if accent else t.TEXT_HI};
            background: transparent;
            border: none;
            font-size: 12px;
            font-weight: 700;
            """
        )
        self._value.setToolTip(value)
        pill_lay.addWidget(self._value, 0, Qt.AlignVCenter)
        lay.addWidget(self._value_pill, 0, Qt.AlignVCenter)

    def set_value(self, value: str) -> None:
        self._value.setText(value)
        self._value.setToolTip(value)

    def value_label(self) -> ElidedLabel:
        return self._value

    def value_pill(self) -> QFrame:
        return self._value_pill


def _compact_count(value: int) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        text = f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if abs_value >= 1_000:
        text = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return str(value)


def _select_primary_file(model: HFModel) -> HFModelFile | None:
    if not model.files:
        return None

    def score(item: HFModelFile) -> tuple[int, int, int]:
        quant = (item.quantization or "").upper()
        return (
            1 if "Q4_K_M" in quant else 0,
            1 if item.size_bytes > 0 else 0,
            item.size_bytes,
        )

    return max(model.files, key=score)


def _format_size(file: HFModelFile | None, model: HFModel) -> str:
    if file and file.size_bytes > 0:
        return f"{file.size_bytes / (1024 ** 3):.1f} GB"
    quant = (file.quantization if file else "") or ""
    if model.params_b > 0 and quant:
        return f"~{estimate_gguf_size_gb(model.params_b, quant):.1f} GB"
    return "Unknown"


def _derive_arch(model: HFModel) -> str:
    haystack = " ".join([model.name, model.id, *model.tags]).lower()
    families = [
        ("gpt-oss", "GPT-OSS"),
        ("qwen", "Qwen"),
        ("llama", "Llama"),
        ("gemma", "Gemma"),
        ("mistral", "Mistral"),
        ("mixtral", "Mixtral"),
        ("deepseek", "DeepSeek"),
        ("phi", "Phi"),
        ("command-r", "Command-R"),
        ("falcon", "Falcon"),
        ("exaone", "EXAONE"),
        ("mamba", "Mamba"),
    ]
    for needle, label in families:
        if needle in haystack:
            return label
    return "GGUF"


def _derive_domain(model: HFModel) -> str:
    tags = [tag.lower() for tag in model.tags]
    haystack = " ".join([model.name, *tags]).lower()
    if "feature-extraction" in tags or "embedding" in haystack:
        return "Embedding"
    if "image-text-to-text" in tags or "multimodal" in haystack or "vision" in haystack:
        return "Multimodal"
    if _CODING_RX.search(haystack):
        return "Coding"
    if _REASONING_RX.search(haystack):
        return "Reasoning"
    if _CHAT_RX.search(haystack):
        return "Chat"
    return "LLM"


class ModelCard(QFrame):
    details_clicked = Signal(HFModel)
    open_hf_clicked = Signal(str)

    def __init__(self, model: HFModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._selected = False
        self._primary_file = _select_primary_file(model)
        self._info_values: dict[str, ElidedLabel] = {}
        self._info_pills: dict[str, QFrame] = {}
        self._meta_values: dict[str, ElidedLabel] = {}

        self.setObjectName("ModelCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumWidth(0)

        root = QVBoxLayout(self)
        self._body_lay = root
        root.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        root.setSpacing(t.SPACE_3)
        self._apply_card_style()

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(t.SPACE_3)

        self._brand_icon = QLabel()
        self._brand_icon.setFixedSize(28, 28)
        self._brand_icon.setPixmap(BrandManager.get_icon(model.name).pixmap(28, 28))
        self._brand_icon.setAlignment(Qt.AlignCenter)
        header.addWidget(self._brand_icon, 0, Qt.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(3)
        self._name = ElidedLabel(model.name)
        self._name.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 850;"
        )
        self._name.setToolTip(model.name)
        title_col.addWidget(self._name)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setContentsMargins(0, 0, 0, 0)
        header_right.setSpacing(10)
        header_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        if model.params_b > 0:
            self._params_badge = QLabel(f"{model.params_b:.1f}B")
            self._params_badge.setStyleSheet(
                f"""
                color: {t.ACCENT_SOFT};
                background: rgba(124,92,255,0.12);
                border: 1px solid rgba(124,92,255,0.28);
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 800;
                """
            )
            header_right.addWidget(self._params_badge, 0, Qt.AlignVCenter)

        self._hf_link = QPushButton("HF ↗")
        self._hf_link.setCursor(Qt.PointingHandCursor)
        self._hf_link.setFlat(True)
        self._hf_link.setProperty("variant", "link")
        self._hf_link.setStyleSheet(
            f"""
            QPushButton {{
                color: {t.ACCENT_HI};
                background: transparent;
                border: none;
                padding: 0;
                font-size: 11px;
                font-weight: 800;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {t.ACCENT}; }}
            """
        )
        self._hf_link.setToolTip("Open on Hugging Face")
        self._hf_link.clicked.connect(lambda _=False, mid=model.id: self.open_hf_clicked.emit(mid))
        header_right.addWidget(self._hf_link, 0, Qt.AlignVCenter)

        header.addLayout(header_right, 0)
        root.addLayout(header)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(t.SPACE_5)
        author_stat = _MetaStat("👤", "Author", model.author)
        likes_stat = _MetaStat("❤️", "Likes", _compact_count(model.likes), accent=True)
        downloads_stat = _MetaStat("⬇️", "Downloads", _compact_count(model.downloads))
        self._meta_values["Author"] = author_stat.value_label()
        self._meta_values["Likes"] = likes_stat.value_label()
        self._meta_values["Downloads"] = downloads_stat.value_label()
        stats_row.addWidget(author_stat, 0)
        stats_row.addWidget(likes_stat, 0)
        stats_row.addWidget(downloads_stat, 0)
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        self._info_panel = QFrame()
        self._info_panel.setObjectName("model-card-info-panel")
        self._info_panel.setStyleSheet(
            f"""
            QFrame#model-card-info-panel {{
                background: #0F1520;
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
            }}
            """
        )
        self._info_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        panel_lay = QVBoxLayout(self._info_panel)
        panel_lay.setContentsMargins(12, 10, 12, 8)
        panel_lay.setSpacing(0)

        panel_header = QHBoxLayout()
        panel_header.setContentsMargins(0, 0, 0, 0)
        panel_header.setSpacing(t.SPACE_2)

        panel_title = QLabel("Model Information")
        panel_title.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 12px; font-weight: 800; padding-bottom: 6px;"
        )
        panel_header.addWidget(panel_title, 0, Qt.AlignVCenter)
        panel_header.addStretch(1)

        self._info_toggle = QPushButton("Show")
        self._info_toggle.setCursor(Qt.PointingHandCursor)
        self._info_toggle.setProperty("variant", "ghost")
        self._info_toggle.setFixedHeight(24)
        self._info_toggle.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                color: {t.TEXT_MID};
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                color: {t.TEXT_HI};
                border-color: rgba(255,255,255,0.14);
                background: rgba(255,255,255,0.04);
            }}
            """
        )
        self._info_toggle.clicked.connect(self._toggle_info_panel)
        panel_header.addWidget(self._info_toggle, 0, Qt.AlignVCenter)
        panel_lay.addLayout(panel_header)

        self._info_body = QWidget()
        self._info_body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        info_body_lay = QVBoxLayout(self._info_body)
        info_body_lay.setContentsMargins(0, 0, 0, 0)
        info_body_lay.setSpacing(0)

        info_rows = [
            ("File", self._display_filename()),
            ("Format", self._display_format()),
            ("Quantization", self._display_quantization()),
            ("Arch", _derive_arch(model)),
            ("Domain", _derive_domain(model)),
            ("Size on disk", _format_size(self._primary_file, model)),
        ]
        for idx, (key, value) in enumerate(info_rows):
            row = _InfoRow(key, value, accent=key in {"Format", "Quantization", "Domain"})
            if idx == len(info_rows) - 1:
                row.setStyleSheet("QWidget#model-card-info-row { background: transparent; border-bottom: none; }")
            info_body_lay.addWidget(row)
            self._info_values[key] = row.value_label()
            self._info_pills[key] = row.value_pill()

        self._info_body.hide()
        panel_lay.addWidget(self._info_body)
        root.addWidget(self._info_panel)

        self._summary = QLabel("Open Settings.")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: 12px; line-height: 1.2;"
        )
        self._summary.hide()
        root.addWidget(self._summary)

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
        self._fit_hint.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: bold;"
        )
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
        root.addWidget(self._fit_panel)

    def _display_filename(self) -> str:
        if not self._primary_file:
            return "No GGUF file"
        return PurePosixPath(self._primary_file.filename).name

    def _display_format(self) -> str:
        return "GGUF" if self._primary_file or any(tag.lower() == "gguf" for tag in self.model.tags) else "Unknown"

    def _display_quantization(self) -> str:
        if self._primary_file and self._primary_file.quantization:
            return self._primary_file.quantization
        return "Unknown"

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
        self._summary.show()

    def set_score_unavailable(self, message: str = "No hardware fit available.") -> None:
        self._fit_panel.hide()
        self._summary.setText(message)
        self._summary.show()

    def set_detail_error(self, message: str) -> None:
        self._fit_panel.hide()
        self._summary.setText(message)
        self._summary.show()

    def _toggle_info_panel(self) -> None:
        expanded = self._info_body.isVisible()
        self._info_body.setVisible(not expanded)
        self._info_toggle.setText("Show" if expanded else "Hide")
        self.updateGeometry()

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
        self._fit_label.setText(
            f"{fit} ({best.get('best_quant')})" if best.get("best_quant") else fit
        )
        self._fit_label.setStyleSheet(
            f"color: {accent}; font-size: 12px; font-weight: bold;"
        )
        self._fit_hint.setText("Also " + " / ".join(also[:2]) if also else "")
        self._fit_accent.setStyleSheet(f"background-color: {accent}; border-radius: 2px;")
        quant = best.get("best_quant")
        if score is None:
            self._summary.setText("Scoring...")
            self._summary.show()
        else:
            self._summary.hide()
        self._fit_panel.show()
