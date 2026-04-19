# Vast.ai Manager

A desktop application for managing **Vast.ai** infrastructure. Built with PySide6 and the official Vast.ai SDK, providing a low-latency interface for instance control, marketplace searching, and remote deployment.

![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)
![OS](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

> [!CAUTION]
> **Warning**: This project is currently in **Pre-Alpha**. It manages real cloud infrastructure and financial expenditures on Vast.ai. Use at your own risk. Features are evolving rapidly and may contain bugs or breaking changes.

---

## 🛠 Features

### 🖥 Instance Management
*   **Real-time Telemetry**: Monitor GPU/CPU load, System RAM, Disk, and Network traffic live.
*   **Thermal Monitoring**: Integrated tracking of hardware temperatures.
*   **Lifecycle Control**: Start, stop, reboot, and label instances directly.
*   **Native Terminal Integration**: Automatic SSH tunneling with one-click terminal launch.

### 🛒 Marketplace & Rental
*   **Advanced Search**: Deep filtering by GPU model (4090, A100, H100), VRAM, CPU architecture, and region.
*   **Workflow Presets**: Quick-filters for ML training, inference, and rendering.
*   **One-Click Deployment**: Automated rental using custom templates, Docker images, and SSH key injection.

### 📊 Analytics & Finance
*   **Spend Tracking**: Aggregated burn rates for 24h, 7 days, and 30 days.
*   **Cycle Monitor**: Track remaining balance against recharge frequency.
*   **Historical Timeline**: Visualized timeline of credit consumption and deposits.

### 🧪 Remote AI Lab
*   **Hardware Gauges**: Visual resource availability meters for GPU and System RAM.
*   **Automated Setup**: One-click scripts to install and configure `LLMfit` and `llama.cpp`.
*   **Model Advisor**: Integrated recommendation engine for GGUF model selection based on local hardware capacity.

---

## 🚀 Installation

### Requirements
*   **OS**: Windows 10/11
*   **Python**: 3.10 or higher
*   **OpenSSH Client**: Must be enabled in Windows Features.
*   **Terminal**: [Windows Terminal](https://aka.ms/terminal) is recommended for the best SSH experience.

### Setup
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Haz4rdovisk/vast.ai-manager.git
    cd vast.ai-manager
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration
1.  Run the application: `python main.py`
2.  In the **Settings** view, enter your **Vast.ai API Key** from your [account page](https://cloud.vast.ai/account/).
3.  Click **Test Connection** to verify availability.
4.  Save and start managing your fleet.

---

## 🏗 Tech Stack
*   **PySide6**: Qt6 framework for high-fidelity native UI.
*   **Vast.ai SDK**: Integration with the underlying cloud API.
*   **Multi-threaded Architecture**: Custom worker system for asynchronous operations and zero-lag interface response.
