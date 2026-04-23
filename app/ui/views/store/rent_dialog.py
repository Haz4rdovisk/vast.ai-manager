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
    ("PyTorch (CUDA 12.4)", "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel"),
    ("PyTorch (CUDA 12.1)", "pytorch/pytorch:2.2.2-cuda12.1-cudnn8-devel"),
    ("NVIDIA CUDA 12.4 devel", "nvidia/cuda:12.4.1-devel-ubuntu22.04"),
    ("NVIDIA CUDA 12.1 devel", "nvidia/cuda:12.1.1-devel-ubuntu22.04"),
    ("NVIDIA CUDA 11.8 devel", "nvidia/cuda:11.8.0-devel-ubuntu22.04"),
    ("TensorFlow GPU", "tensorflow/tensorflow:2.16.1-gpu"),
    ("Ubuntu 22.04", "ubuntu:22.04"),
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

        title = QLabel(f"{offer.num_gpus}x {offer.gpu_name} - ${offer.effective_price():.3f}/h")
        title.setProperty("role", "title")
        root.addWidget(title)

        meta = QLabel(" | ".join(x for x in (offer.country, offer.datacenter, offer.hosting_type) if x))
        meta.setProperty("role", "muted")
        root.addWidget(meta)

        root.addWidget(self._section("Machine Image"))
        
        self.template_cb = QComboBox()
        self.template_cb.addItem("1. Select an environment or community template", None)
        for label, img in DEFAULT_IMAGES:
            self.template_cb.addItem(label, {"image": img, "template_hash": None})
        root.addWidget(self.template_cb)

        self.vast_base_cb = QComboBox()
        self.vast_base_cb.addItem("2. Or use Vast's Official Python Base Image", None)
        self.vast_base_cb.addItem("Vast Base - CUDA 13.2 (cuda-13.2.0-auto)", "vastai/base-image:cuda-13.2.0-auto")
        self.vast_base_cb.addItem("Vast Base - CUDA 12.4 (cuda-12.4.1-auto)", "vastai/base-image:cuda-12.4.1-auto")
        self.vast_base_cb.addItem("Vast Base - CUDA 12.1 (cuda-12.1.1-auto)", "vastai/base-image:cuda-12.1.1-auto")
        self.vast_base_cb.addItem("Vast Base - CUDA 11.8 (cuda-11.8.0-auto)", "vastai/base-image:cuda-11.8.0-auto")
        root.addWidget(self.vast_base_cb)

        self.custom_image = QLineEdit()
        self.custom_image.setPlaceholderText("3. Or paste a Custom Docker image URL")
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
            # Filter out known broken template images (Vast.ai natively deleted theirs)
            if tpl.image and any(x in tpl.image for x in ["vastai/", "runpod/", "ghcr.io/selkies"]):
                continue
            self.template_cb.addItem(
                tpl.name,
                {"image": tpl.image, "template_hash": tpl.hash_id},
            )

    def set_ssh_keys(self, keys: list[SshKey], local_pub_key: str | None = None) -> None:
        self.ssh_cb.clear()
        if not keys:
            self.ssh_cb.addItem("No SSH keys on account", None)
            return
            
        self.ssh_cb.addItem("No SSH key selected (uses account defaults)", None)
        
        local_match_id = None
        if local_pub_key:
            # Match by fingerprint or content (prefix)
            pub_clean = local_pub_key.strip().split()[:2]
            for key in keys:
                k_clean = key.public_key.strip().split()[:2]
                if pub_clean == k_clean:
                    local_match_id = key.id
                    break

        for key in keys:
            label = key.label or key.public_key[:38] or f"Key #{key.id}"
            if key.id == local_match_id:
                label = f"✓ {label} (Current Local Key)"
            self.ssh_cb.addItem(label, key.id)
            
        # If we found a match, pre-select it
        if local_match_id is not None:
            idx = self.ssh_cb.findData(local_match_id)
            if idx >= 0:
                self.ssh_cb.setCurrentIndex(idx)

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
        base_data = self.vast_base_cb.currentData()
        image = self.custom_image.text().strip()
        template_hash = None

        # Priority 1: Custom Image (already in `image` variable)
        # Priority 2: Vast Base Dropdown
        if not image and base_data:
            image = base_data
        # Priority 3: Community/Default Template Dropdown
        elif not image and isinstance(data, dict):
            image = data.get("image") or ""
            template_hash = data.get("template_hash")
            
        if not image and not template_hash:
            self.custom_image.setPlaceholderText("Required: choose an image or paste a Docker image")
            self.custom_image.setFocus()
            return

        import re
        from PySide6.QtWidgets import QMessageBox

        if image and self.offer.cuda_max_good:
            match = re.search(r'cuda[-_:]?(\d+\.\d+)', image, re.IGNORECASE)
            if match:
                try:
                    req_cuda = float(match.group(1))
                    if req_cuda > self.offer.cuda_max_good:
                        QMessageBox.warning(
                            self,
                            "CUDA Version Conflict",
                            f"This image requires CUDA {req_cuda}, but the selected instance only supports up to CUDA {self.offer.cuda_max_good}.\n\nPlease choose an older CUDA image or rent a different machine.",
                        )
                        return
                except ValueError:
                    pass

        self.confirmed.emit(
            RentRequest(
                offer_id=self.offer.ask_contract_id,
                image=image or None,
                template_hash=template_hash,
                disk_gb=float(self.disk.value()),
                label=self.label_in.text().strip() or None,
                ssh_key_id=self.ssh_cb.currentData(),
                env=self._parse_env(),
                onstart_cmd=self.onstart.toPlainText().strip() or None,
                jupyter_lab=self.jupyter.isChecked(),
                runtype="jupyter" if self.jupyter.isChecked() else "ssh",
                price=float(self.bid_price.value())
                if self.offer.min_bid is not None and self.bid_price.value() > 0
                else None,
            )
        )
        self.accept()

