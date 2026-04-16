"""Local design tokens + QSS fragment for the Lab workspace.
Deliberately separate from app/theme.py — different visual language."""
from __future__ import annotations

# Deep charcoals with a blue undertone; surfaces layer via lightness, not hue.
BG_DEEP     = "#07090D"   # shell background
BG_BASE     = "#0C1016"   # content area
SURFACE_1   = "#141922"   # cards
SURFACE_2   = "#1C2330"   # elevated / hover
SURFACE_3   = "#262F3F"   # pressed / inputs
BORDER_LOW  = "#1B2230"
BORDER_MED  = "#2A3345"
BORDER_HI   = "#3B4662"

TEXT_HI     = "#F1F4FA"
TEXT        = "#C7CEDC"
TEXT_MID    = "#8891A6"
TEXT_LOW    = "#5A6277"

ACCENT      = "#7C5CFF"   # iris
ACCENT_HI   = "#9B83FF"
ACCENT_GLOW = "rgba(124, 92, 255, 0.35)"

OK          = "#3BD488"
WARN        = "#F4B740"
ERR         = "#F0556A"
INFO        = "#4EA8FF"

RADIUS_SM   = 6
RADIUS_MD   = 10
RADIUS_LG   = 14
RADIUS_XL   = 20

SPACE_1     = 4
SPACE_2     = 8
SPACE_3     = 12
SPACE_4     = 16
SPACE_5     = 24
SPACE_6     = 32
SPACE_7     = 48

FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"


def health_color(level: str) -> str:
    return {"ok": OK, "warn": WARN, "err": ERR, "info": INFO}.get(level, TEXT_MID)


# Scoped to widgets with objectName starting with "lab-". Won't leak into Cloud.
STYLESHEET = f"""
#lab-shell {{
    background-color: {BG_DEEP};
    color: {TEXT};
    font-family: {FONT_DISPLAY};
    font-size: 10pt;
}}
#lab-shell QLabel {{ background: transparent; color: {TEXT}; }}
#lab-shell QLabel[role="display"] {{
    color: {TEXT_HI};
    font-size: 22pt;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
#lab-shell QLabel[role="title"] {{
    color: {TEXT_HI};
    font-size: 14pt;
    font-weight: 600;
}}
#lab-shell QLabel[role="section"] {{
    color: {TEXT_MID};
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}
#lab-shell QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    color: {TEXT};
}}
#lab-shell QLabel[role="muted"] {{ color: {TEXT_MID}; }}

#lab-shell QFrame[role="card"] {{
    background-color: {SURFACE_1};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_LG}px;
}}
#lab-shell QFrame[role="card-raised"] {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_LG}px;
}}

#lab-shell QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 18px;
    font-weight: 600;
}}
#lab-shell QPushButton:hover {{ background-color: {ACCENT_HI}; }}
#lab-shell QPushButton:disabled {{
    background-color: {SURFACE_3}; color: {TEXT_LOW};
}}
#lab-shell QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_MED};
}}
#lab-shell QPushButton[variant="ghost"]:hover {{
    background-color: {SURFACE_2}; border-color: {BORDER_HI};
}}
#lab-shell QPushButton[variant="danger"] {{ background-color: {ERR}; }}

#lab-shell QLineEdit, #lab-shell QComboBox, #lab-shell QSpinBox {{
    background-color: {SURFACE_3};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    padding: 8px 12px;
}}
#lab-shell QLineEdit:focus, #lab-shell QComboBox:focus {{ border-color: {ACCENT}; }}

#lab-nav-rail {{
    background-color: {BG_BASE};
    border-right: 1px solid {BORDER_LOW};
}}
#lab-nav-rail QPushButton[role="nav-item"] {{
    background-color: transparent;
    color: {TEXT_MID};
    text-align: left;
    padding: 12px 18px;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-weight: 500;
}}
#lab-nav-rail QPushButton[role="nav-item"]:hover {{
    color: {TEXT_HI};
    background-color: {SURFACE_1};
}}
#lab-nav-rail QPushButton[role="nav-item"][active="true"] {{
    color: {TEXT_HI};
    background-color: {SURFACE_2};
    border-left: 2px solid {ACCENT};
}}

#lab-shell QScrollArea {{ border: none; background: transparent; }}
#lab-shell QScrollBar:vertical {{ background: transparent; width: 8px; }}
#lab-shell QScrollBar::handle:vertical {{
    background: {BORDER_MED}; border-radius: 4px; min-height: 28px;
}}
#lab-shell QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
#lab-shell QScrollBar::add-line, #lab-shell QScrollBar::sub-line {{ height: 0; }}
"""
