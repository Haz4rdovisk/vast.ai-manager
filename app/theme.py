"""Unified design system for Vast.ai Manager — Premium Black Glassmorphism.
All design tokens, color helpers, and the global QSS live here."""
from __future__ import annotations

# ━━ Surfaces ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BG_VOID    = "#030508"
BG_DEEP    = "#070A0F"
BG_BASE    = "#0B0F17"

# Glass surfaces — rgba for conceptual reference; QSS uses solid fallbacks.
# Actual glass blur is handled via QPainter overrides in components.
SURFACE_1       = "#0F141E"          # card (solid fallback)
SURFACE_2       = "#161C2A"          # raised card
SURFACE_3       = "#1E2637"          # inputs / recessed
GLASS_HOVER     = "#283246"          # hover overlay

SURFACE_1_RGBA  = "rgba(15, 20, 30, 0.65)"
SURFACE_2_RGBA  = "rgba(22, 28, 42, 0.55)"
SURFACE_3_RGBA  = "rgba(30, 38, 55, 0.50)"

# ━━ Borders ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BORDER_GLOW = "rgba(124, 92, 255, 0.15)"
BORDER_LOW  = "rgba(255,255,255, 0.04)"
BORDER_MED  = "rgba(255,255,255, 0.08)"
BORDER_HI   = "rgba(255,255,255, 0.14)"

# ━━ Typography ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEXT_HERO = "#FFFFFF"
TEXT_HI   = "#F1F4FA"
TEXT      = "#C7CEDC"
TEXT_MID  = "#6B7590"
TEXT_LOW  = "#3D4560"

FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"

FONT_SIZE_DISPLAY = 28   # page titles
FONT_SIZE_TITLE   = 16   # card titles
FONT_SIZE_BODY    = 14   # body text
FONT_SIZE_LABEL   = 11   # labels (uppercase, tracking 1.5px)
FONT_SIZE_SMALL   = 12   # secondary
FONT_SIZE_MONO    = 13   # code / values

# ━━ Accent + Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCENT      = "#7C5CFF"
ACCENT_HI   = "#9B83FF"
ACCENT_SOFT = "#B3A0FF"
ACCENT_GLOW = "rgba(124, 92, 255, 0.25)"
ACCENT_END  = "#5A8AFF"       # gradient endpoint

OK   = "#3BD488"
WARN = "#F4B740"
ERR  = "#F0556A"
INFO = "#4EA8FF"
LIVE = "#19C37D"

# ━━ Geometry ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL, RADIUS_PILL = 8, 12, 16, 24, 999
SPACE_1, SPACE_2, SPACE_3, SPACE_4 = 4, 8, 12, 16
SPACE_5, SPACE_6, SPACE_7, SPACE_8 = 24, 32, 48, 64

TITLEBAR_HEIGHT = 38
TITLEBAR_BG     = "transparent"

# ━━ Animation durations (ms) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANIM_FAST   = 150
ANIM_NORMAL = 250
ANIM_SLOW   = 400
ANIM_GAUGE  = 800

# ━━ Shadow tokens (descriptive, for QPainter helpers) ━━━━━━━━━━━━━━━━━━━━━━━
SHADOW_BLUR_SM  = 8
SHADOW_BLUR_MD  = 32
SHADOW_BLUR_LG  = 48
SHADOW_OFFSET_Y = 8


# ━━ Color helpers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
    """4-tier scale: <1h CRITICAL, 1-6h LOW, 6-24h MEDIUM, >24h GOOD."""
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
    return {
        "ok": OK, "warn": WARN, "err": ERR,
        "info": INFO, "live": LIVE, "unknown": TEXT_MID,
    }.get(level, TEXT_MID)


# ━━ Global stylesheet ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STYLESHEET = f"""
/* ── Base ──────────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget#app-shell {{
    background-color: {BG_DEEP};
    color: {TEXT};
    font-family: {FONT_DISPLAY};
    font-size: {FONT_SIZE_BODY}px;
}}
QWidget {{ color: {TEXT}; }}

/* ── Labels ────────────────────────────────────────────────────────────── */
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel[role="display"] {{
    color: {TEXT_HERO};
    font-size: {FONT_SIZE_DISPLAY}px;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
QLabel[role="title"] {{
    color: {TEXT_HI};
    font-size: {FONT_SIZE_TITLE}px;
    font-weight: 600;
}}
QLabel[role="section"] {{
    color: {TEXT_MID};
    font-size: {FONT_SIZE_LABEL}px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_MONO}px;
    color: {TEXT};
}}
QLabel[role="muted"] {{ color: {TEXT_MID}; }}

/* ── Cards (transparent — QPainter handles glass effect) ───────────── */
QFrame[role="card"] {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_LG}px;
}}
QFrame[role="card-raised"] {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_LG}px;
}}

/* ── Buttons ───────────────────────────────────────────────────────────── */
/* Primary (default): accent gradient with subtle hairline highlight */
QPushButton {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {ACCENT_HI}, stop:1 {ACCENT}
    );
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: {RADIUS_MD}px;
    padding: 9px 18px;
    font-weight: 600;
    font-size: {FONT_SIZE_BODY}px;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {ACCENT_SOFT}, stop:1 {ACCENT_HI}
    );
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {ACCENT}, stop:1 #4B3ACC
    );
    border-color: rgba(0, 0, 0, 0.30);
    padding-top: 10px;
    padding-bottom: 8px;
}}
QPushButton:focus {{
    outline: none;
    border: 1px solid {ACCENT_SOFT};
}}
QPushButton:disabled {{
    background-color: {SURFACE_2};
    color: {TEXT_LOW};
    border: 1px solid {BORDER_LOW};
}}

/* Ghost: transparent with hairline border */
QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_MED};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: rgba(255, 255, 255, 0.04);
    border-color: {BORDER_HI};
    color: {TEXT_HI};
}}
QPushButton[variant="ghost"]:pressed {{
    background-color: rgba(255, 255, 255, 0.02);
    border-color: {BORDER_MED};
}}
QPushButton[variant="ghost"]:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton[variant="ghost"]:disabled {{
    color: {TEXT_LOW};
    border-color: {BORDER_LOW};
    background: transparent;
}}

/* Secondary: filled surface with border */
QPushButton[variant="secondary"] {{
    background-color: {SURFACE_2};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {GLASS_HOVER};
    border-color: {BORDER_HI};
}}
QPushButton[variant="secondary"]:pressed {{
    background-color: {SURFACE_3};
}}
QPushButton[variant="secondary"]:focus {{
    border: 1px solid {ACCENT};
}}

/* Danger: destructive actions */
QPushButton[variant="danger"] {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #F06A7C, stop:1 {ERR}
    );
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.10);
}}
QPushButton[variant="danger"]:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #F4808F, stop:1 #E84C60
    );
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton[variant="danger"]:pressed {{
    background-color: #C53A4D;
    border-color: rgba(0, 0, 0, 0.30);
    padding-top: 10px;
    padding-bottom: 8px;
}}
QPushButton[variant="danger"]:focus {{
    border: 1px solid #F4808F;
}}

/* Small size modifier */
QPushButton[size="sm"] {{
    padding: 5px 12px;
    font-size: {FONT_SIZE_SMALL}px;
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {SURFACE_3};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    padding: 8px 14px;
    font-size: {FONT_SIZE_BODY}px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_2};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    selection-background-color: {ACCENT};
    padding: 4px;
}}

/* ── Console ───────────────────────────────────────────────────────────── */
QTextEdit#console {{
    background-color: {BG_VOID};
    color: {TEXT};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_MD}px;
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_MONO}px;
    padding: 10px 12px;
}}

/* ── NavRail ───────────────────────────────────────────────────────────── */
/* Entire nav rail is custom-painted; items are custom widgets with their
   own hover/active rendering. Keep only the frame reset here. */
QFrame#nav-rail {{
    background: transparent;
    border: none;
}}

/* ── Scroll ─────────────────────────────────────────────────────────────── */
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    border: none;
    background-color: {BG_DEEP};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_MED};
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_MED};
    border-radius: 3px;
}}

/* ── Checkboxes ────────────────────────────────────────────────────────── */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {BORDER_MED};
    border-radius: 5px;
    background: {SURFACE_3};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {BORDER_HI};
}}

/* ── MessageBox ────────────────────────────────────────────────────────── */
QMessageBox QLabel {{ color: {TEXT}; }}

/* ── Title Bar ─────────────────────────────────────────────────────────── */
QWidget#title-bar {{
    background-color: transparent;
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
    font-size: 12px;
    font-weight: 400;
}}
QPushButton#title-btn:hover {{
    background-color: {SURFACE_1};
    color: {TEXT_HI};
}}
QPushButton#title-btn-close:hover {{
    background-color: {ERR};
    color: white;
}}

/* ── ProgressBar default ───────────────────────────────────────────────── */
QProgressBar {{
    background: {SURFACE_3};
    border: none;
    border-radius: 4px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    border-radius: 4px;
}}

/* ── Tooltip ───────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {SURFACE_2};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_SM}px;
    padding: 12px 14px;
    font-size: 14px;
}}
"""

# ━━ Back-compat aliases ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Keep the existing Cloud UI code importable during transition.
TEXT_SECONDARY = TEXT_MID
SUCCESS = OK
WARNING = WARN
DANGER = ERR
BG = BG_DEEP
CARD_BG = SURFACE_1
CARD_BORDER = BORDER_MED
ACCENT_HOVER = ACCENT_HI
LOG_BG = BG_DEEP
