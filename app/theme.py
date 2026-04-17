"""Unified design system for Vast.ai Manager. One theme for the whole app —
scoped stylesheets and per-workspace QSS are gone."""
from __future__ import annotations

# ---- Surfaces ----------------------------------------------------------------
BG_DEEP    = "#07090D"
BG_BASE    = "#0C1016"
SURFACE_1  = "#141922"
SURFACE_2  = "#1C2330"
SURFACE_3  = "#262F3F"
BORDER_LOW = "#1B2230"
BORDER_MED = "#2A3345"
BORDER_HI  = "#3B4662"

# ---- Typography --------------------------------------------------------------
TEXT_HI  = "#F1F4FA"
TEXT     = "#C7CEDC"
TEXT_MID = "#8891A6"
TEXT_LOW = "#5A6277"

FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"

# ---- Accent + status ---------------------------------------------------------
ACCENT      = "#7C5CFF"
ACCENT_HI   = "#9B83FF"
ACCENT_GLOW = "rgba(124, 92, 255, 0.35)"

OK   = "#3BD488"
WARN = "#F4B740"
ERR  = "#F0556A"
INFO = "#4EA8FF"
LIVE = "#19C37D"  # "alive / tunneled" indicator

# ---- Geometry ----------------------------------------------------------------
RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL = 6, 10, 14, 20
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6, SPACE_7 = 4, 8, 12, 16, 24, 32, 48

TITLEBAR_HEIGHT = 38
TITLEBAR_BG = BG_BASE


# ---- Semantic color helpers --------------------------------------------------
def metric_color(percent: float | None) -> str:
    if percent is None:
        return TEXT_MID
    if percent < 60:
        return OK
    if percent < 85:
        return WARN
    return ERR


def temp_color(temp: float | None) -> str:
    if temp is None:
        return TEXT_MID
    if temp < 70:
        return OK
    if temp < 80:
        return WARN
    return ERR


def autonomy_color(hours: float | None) -> str:
    """4-tier scale preserved from the pre-migration theme:
    <1h = CRITICAL, 1-6h = LOW, 6-24h = MEDIUM, >24h = GOOD."""
    if hours is None:
        return TEXT_MID
    if hours > 24:
        return OK
    if hours > 6:
        return WARN
    if hours > 1:
        return "#ff9800"
    return ERR


def health_color(level: str) -> str:
    return {"ok": OK, "warn": WARN, "err": ERR, "info": INFO, "live": LIVE}.get(level, TEXT_MID)


# ---- Global stylesheet -------------------------------------------------------
STYLESHEET = f"""
QMainWindow, QDialog, QWidget#app-shell {{
    background-color: {BG_DEEP};
    color: {TEXT};
    font-family: {FONT_DISPLAY};
    font-size: 10pt;
}}
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel[role="display"] {{
    color: {TEXT_HI};
    font-size: 22pt;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
QLabel[role="title"] {{
    color: {TEXT_HI};
    font-size: 14pt;
    font-weight: 600;
}}
QLabel[role="section"] {{
    color: {TEXT_MID};
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}
QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    color: {TEXT};
}}
QLabel[role="muted"] {{ color: {TEXT_MID}; }}

QFrame[role="card"] {{
    background-color: {SURFACE_1};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_LG}px;
}}
QFrame[role="card-raised"] {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_LG}px;
}}

QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {ACCENT_HI}; }}
QPushButton:disabled {{ background-color: {SURFACE_3}; color: {TEXT_LOW}; }}
QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_MED};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {SURFACE_2};
    border-color: {BORDER_HI};
}}
QPushButton[variant="danger"] {{ background-color: {ERR}; }}
QPushButton[variant="danger"]:hover {{ background-color: #d63a4d; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {SURFACE_3};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    padding: 8px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}

QTextEdit#console {{
    background-color: {BG_DEEP};
    color: {TEXT};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_MD}px;
    font-family: {FONT_MONO};
    font-size: 9pt;
    padding: 8px 10px;
}}

QFrame#nav-rail {{
    background-color: {BG_BASE};
    border-right: 1px solid {BORDER_LOW};
}}
QFrame#nav-rail QPushButton[role="nav-item"] {{
    background-color: transparent;
    color: {TEXT_MID};
    text-align: left;
    padding: 12px 18px;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-weight: 500;
}}
QFrame#nav-rail QPushButton[role="nav-item"]:hover {{
    color: {TEXT_HI};
    background-color: {SURFACE_1};
}}
QFrame#nav-rail QPushButton[role="nav-item"][active="true"] {{
    color: {TEXT_HI};
    background-color: {SURFACE_2};
    border-left: 2px solid {ACCENT};
}}

QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    border: none;
    background-color: {BG_DEEP};
}}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_MED}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_MED};
    border-radius: 4px;
    background: {SURFACE_3};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QMessageBox QLabel {{ color: {TEXT}; }}

/* Title Bar */
QWidget#title-bar {{
    background-color: {TITLEBAR_BG};
    border-bottom: 1px solid {BORDER_LOW};
}}
QPushButton#title-btn, QPushButton#title-btn-close {{
    background-color: transparent;
    color: {TEXT_MID};
    border: none;
    border-radius: 0;
    width: 46px;
    height: {TITLEBAR_HEIGHT}px;
    padding: 0;
    font-size: 11pt;
}}
QPushButton#title-btn:hover {{
    background-color: {SURFACE_1};
    color: {TEXT_HI};
}}
QPushButton#title-btn-close:hover {{
    background-color: {ERR};
    color: white;
}}
"""

# ---- Back-compat aliases (Phase 0 transition) --------------------------------
# These keep the existing Cloud UI code importable during Phases 1-4.
# Removed once Cloud widgets are replaced.
TEXT_SECONDARY = TEXT_MID
SUCCESS = OK
WARNING = WARN
DANGER = ERR
BG = BG_DEEP
CARD_BG = SURFACE_1
CARD_BORDER = BORDER_MED
ACCENT_HOVER = ACCENT_HI
LOG_BG = BG_DEEP

