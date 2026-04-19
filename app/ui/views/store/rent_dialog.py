"""Rent confirmation dialog for Vast marketplace offers."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.models_rental import Offer, RentRequest, SshKey, Template


DEFAULT_IMAGES: list[tuple[str, str]] = [
    ("PyTorch CUDA 12.4", "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel"),
    ("NVIDIA CUDA 12.4 devel", "nvidia/cuda:12.4.1-devel-ubuntu22.04"),
    ("TensorFlow GPU", "tensorflow/tensorflow:2.16.1-gpu"),
    ("Ubuntu 22.04", "vastai/ubuntu:22.04"),
    ("vLLM OpenAI", "vllm/vllm-openai:latest"),
]


class RentDialog(QDialog):
    confirmed = Signal(object)  # RentRequest

    def __init__(self, offer: Offer, parent=None):
        super().__init__(parent)
        self.offer = offer
        self.setWindowTitle(f"Rent offer #{offer.id}")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
        root.setSpacing(t.SPACE_4)

        title = QLabel(f"{offer.num_gpus}x {offer.gpu_name} - ${offer.dph_total:.3f}/h")
        title.setProperty("role", "title")
        root.addWidget(title)

        meta = QLabel(" | ".join(x for x in (offer.country, offer.datacenter, offer.hosting_type) if x))
        meta.setProperty("role", "muted")
        root.addWidget(meta)

        root.addWidget(self._section("Image"))
        self.template_cb = QComboBox()
        self.template_cb.addItem("Select an image or template", None)
        for label, image in DEFAULT_IMAGES:
            self.template_cb.addItem(label, {"image": image, "template_hash": None})
        root.addWidget(self.template_cb)

        self.custom_image = QLineEdit()
        self.custom_image.setPlaceholderText("Custom Docker image, optional")
        root.addWidget(self.custom_image)

        fields = QWidget()
        fields_lay = QHBoxLayout(fields)
        fields_lay.setContentsMargins(0, 0, 0, 0)
        fields_lay.setSpacing(t.SPACE_3)
        self.disk = QDoubleSpinBox()
        self.disk.setRange(5, 10000)
        self.disk.setDecimals(0)
        self.disk.setValue(20)
        self.disk.setSuffix(" GB disk")
        self.label_in = QLineEdit()
        self.label_in.setPlaceholderText("Label, optional")
        fields_lay.addWidget(self.disk)
        fields_lay.addWidget(self.label_in, 1)
        root.addWidget(fields)

        self.bid_price = QDoubleSpinBox()
        self.bid_price.setRange(0, 50)
        self.bid_price.setDecimals(3)
        self.bid_price.setSingleStep(0.01)
        self.bid_price.setSuffix(" $/h bid")
        if offer.min_bid is not None:
            self.bid_price.setValue(float(offer.min_bid))
            root.addWidget(self.bid_price)

        root.addWidget(self._section("SSH Key"))
        self.ssh_cb = QComboBox()
        self.ssh_cb.addItem("No SSH key selected", None)
        root.addWidget(self.ssh_cb)

        root.addWidget(self._section("Advanced"))
        self.jupyter = QCheckBox("Enable Jupyter Lab")
        root.addWidget(self.jupyter)
        self.onstart = QPlainTextEdit()
        self.onstart.setPlaceholderText("onstart script, optional")
        self.onstart.setFixedHeight(76)
        root.addWidget(self.onstart)
        self.env_in = QLineEdit()
        self.env_in.setPlaceholderText("Env vars: KEY=value OTHER=value")
        root.addWidget(self.env_in)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Rent now")
        confirm.clicked.connect(self._confirm)
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        root.addLayout(actions)

    def set_templates(self, templates: list[Template]) -> None:
        existing = {
            self.template_cb.itemData(i).get("template_hash")
            for i in range(self.template_cb.count())
            if isinstance(self.template_cb.itemData(i), dict)
        }
        for tpl in templates[:30]:
            if not tpl.hash_id or tpl.hash_id in existing:
                continue
            self.template_cb.addItem(
                tpl.name,
                {"image": tpl.image, "template_hash": tpl.hash_id},
            )

    def set_ssh_keys(self, keys: list[SshKey]) -> None:
        self.ssh_cb.clear()
        if not keys:
            self.ssh_cb.addItem("No SSH keys on account", None)
            return
        self.ssh_cb.addItem("No SSH key selected", None)
        for key in keys:
            label = key.label or key.public_key[:38] or f"Key #{key.id}"
            self.ssh_cb.addItem(label, key.id)

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "section")
        return label

    def _parse_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for token in self.env_in.text().split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            key = key.strip()
            if key:
                env[key] = value.strip()
        return env

    def _confirm(self) -> None:
        data = self.template_cb.currentData()
        image = self.custom_image.text().strip()
        template_hash = None
        if isinstance(data, dict):
            image = image or data.get("image") or ""
            template_hash = data.get("template_hash")
        if not image and not template_hash:
            self.custom_image.setPlaceholderText("Required: choose an image or paste a Docker image")
            self.custom_image.setFocus()
            return
        self.confirmed.emit(
            RentRequest(
                offer_id=self.offer.id,
                image=image or None,
                template_hash=template_hash,
                disk_gb=float(self.disk.value()),
                label=self.label_in.text().strip() or None,
                ssh_key_id=self.ssh_cb.currentData(),
                env=self._parse_env(),
                onstart_cmd=self.onstart.toPlainText().strip() or None,
                jupyter_lab=self.jupyter.isChecked(),
                price=float(self.bid_price.value())
                if self.offer.min_bid is not None and self.bid_price.value() > 0
                else None,
            )
        )
        self.accept()

