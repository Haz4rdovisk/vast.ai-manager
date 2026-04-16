from __future__ import annotations

# Palette
BG = "#1a1a2e"
CARD_BG = "#16213e"
CARD_BORDER = "#0f3460"
ACCENT = "#6C63FF"
ACCENT_HOVER = "#7D75FF"
TEXT = "#EAEAEA"
TEXT_SECONDARY = "#9AA0B4"
SUCCESS = "#00d26a"
WARNING = "#ffc107"
DANGER = "#f44336"
INFO = "#3ea6ff"
LOG_BG = "#0d0d1a"


def metric_color(percent: float | None) -> str:
    if percent is None:
        return TEXT_SECONDARY
    if percent < 60:
        return SUCCESS
    if percent < 85:
        return WARNING
    return DANGER


def temp_color(temp: float | None) -> str:
    if temp is None:
        return TEXT_SECONDARY
    if temp < 70:
        return SUCCESS
    if temp < 80:
        return WARNING
    return DANGER


def autonomy_color(hours: float | None) -> str:
    """
    Retorna a cor baseada no nível de autonomia.
    
    - CRITICAL (< 1h): Vermelho (DANGER)
    - LOW (1-6h): Laranja (#ff9800)
    - MEDIUM (6-24h): Amarelo (WARNING)
    - GOOD (> 24h): Verde (SUCCESS)
    """
    if hours is None:
        return TEXT_SECONDARY
    if hours > 24:
        return SUCCESS
    if hours > 6:
        return WARNING
    if hours > 1:
        return "#ff9800"  # Laranja para LOW (1-6h)
    return DANGER  # CRITICAL (< 1h)


STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}}
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; }}
QLabel#secondary {{ color: {TEXT_SECONDARY}; }}
QLabel#h1 {{ font-size: 18pt; font-weight: 700; letter-spacing: -0.5px; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; }}
QLabel#mono {{ font-family: Consolas, "Courier New", monospace; font-size: 10pt; }}

QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton:disabled {{ background-color: #3a3a4e; color: {TEXT_SECONDARY}; }}
QPushButton#secondary {{
    background-color: transparent;
    border: 1px solid {CARD_BORDER};
    color: {TEXT};
}}
QPushButton#secondary:hover {{ background-color: {CARD_BORDER}; }}
QPushButton#danger {{ background-color: {DANGER}; }}
QPushButton#danger:hover {{ background-color: #d32f2f; }}

QFrame#card {{
    background-color: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 12px;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 6px;
    padding: 7px 10px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {CARD_BG};
    color: {TEXT};
    selection-background-color: {ACCENT};
    border: 1px solid {CARD_BORDER};
}}

QTextEdit#log {{
    background-color: {LOG_BG};
    color: {TEXT};
    border: 1px solid {CARD_BORDER};
    border-radius: 8px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 9pt;
    padding: 6px;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {CARD_BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QMessageBox {{ background-color: {CARD_BG}; }}
QMessageBox QLabel {{ color: {TEXT}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {CARD_BORDER};
    border-radius: 4px;
    background: {BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
"""
