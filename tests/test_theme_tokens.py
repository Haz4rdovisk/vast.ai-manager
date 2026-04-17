"""Locks in the unified design-system palette so refactors can't accidentally
drop a token or change a hex. Runs before any theme edit so the failure is real."""
import re
from app import theme


def test_core_palette_present():
    assert theme.BG_DEEP == "#07090D"
    assert theme.BG_BASE == "#0C1016"
    assert theme.SURFACE_1 == "#141922"
    assert theme.SURFACE_2 == "#1C2330"
    assert theme.SURFACE_3 == "#262F3F"
    assert theme.ACCENT == "#7C5CFF"


def test_text_scale_present():
    assert theme.TEXT_HI == "#F1F4FA"
    assert theme.TEXT == "#C7CEDC"
    assert theme.TEXT_MID == "#8891A6"
    assert theme.TEXT_LOW == "#5A6277"


def test_status_colors_present():
    assert theme.OK == "#3BD488"
    assert theme.WARN == "#F4B740"
    assert theme.ERR == "#F0556A"
    assert theme.INFO == "#4EA8FF"
    assert theme.LIVE == "#19C37D"


def test_metric_color_tiers():
    assert theme.metric_color(10) == theme.OK
    assert theme.metric_color(70) == theme.WARN
    assert theme.metric_color(95) == theme.ERR
    assert theme.metric_color(None) == theme.TEXT_MID


def test_autonomy_color_tiers():
    """Preserves the 4-tier scale from the old app/theme.py."""
    assert theme.autonomy_color(0.5) == theme.ERR
    assert theme.autonomy_color(3.0) == "#ff9800"
    assert theme.autonomy_color(12.0) == theme.WARN
    assert theme.autonomy_color(48.0) == theme.OK
    assert theme.autonomy_color(None) == theme.TEXT_MID


def test_stylesheet_has_lab_shell_scope_removed():
    """Phase 0 ends with the lab-shell scope removed from the main stylesheet —
    the design system now applies globally."""
    assert "#lab-shell" not in theme.STYLESHEET
    assert "QMainWindow" in theme.STYLESHEET  # global rules are back
