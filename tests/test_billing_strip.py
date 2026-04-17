"""BillingStrip renders the same numbers as the old BillingHeader but using
the new design tokens. Tests assert text content, not styling."""
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.views.billing_strip import BillingStrip
from app.models import AppConfig, UserInfo, Instance, InstanceState


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _inst(iid=1, dph=0.5, state=InstanceState.RUNNING):
    return Instance(
        id=iid, state=state, gpu_name="RTX 3090",
        num_gpus=1, gpu_ram_gb=24, image="base", dph=dph,
    )


def test_renders_balance(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=12.34, email="x"), [], 0.0)
    assert "12.34" in s.balance_lbl.text()


def test_renders_burn_and_autonomy(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=10.0, email="x"),
                    [_inst(dph=1.0)], today_spend=2.0)
    assert "1." in s.burn_lbl.text()
    assert "Autonomia" in s.autonomy_lbl.text()


def test_today_spend(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=5.0, email="x"), [], 1.23)
    assert "1.23" in s.today_lbl.text()
