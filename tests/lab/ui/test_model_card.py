from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from app.lab.services.huggingface import HFModel
from app.ui.components.model_card import ModelCard


def _m(name="x-gguf", tags=None):
    return HFModel(
        id=f"a/{name}",
        author="a",
        name=name,
        downloads=1,
        likes=1,
        tags=tags or [],
        files=[],
    )


def test_card_selection_state(qt_app):
    card = ModelCard(_m())
    assert card.is_selected() is False
    card.set_selected(True)
    assert card.is_selected() is True


def test_card_installed_and_installing_state(qt_app):
    card = ModelCard(_m())
    card.show()
    assert card._installed_chip.isVisible() is False
    card.set_installed_on([42])
    assert card._installed_chip.isVisible() is True
    assert "42" in card._installed_chip.text()
    card.set_installing(iid=42, percent=37)
    assert card._install_chip.text().startswith("37%")
    assert card._install_chip.isVisible() is True


def test_card_click_emits_details_signal(qt_app):
    model = _m()
    card = ModelCard(model)
    spy = QSignalSpy(card.details_clicked)
    card._details_btn.click()
    assert spy.count() == 1
    assert spy.at(0)[0] == model


def test_whole_card_click_emits_details_signal(qt_app):
    model = _m()
    card = ModelCard(model)
    card.show()
    spy = QSignalSpy(card.details_clicked)
    QTest.mouseClick(card, Qt.LeftButton)
    assert spy.count() == 1
    assert spy.at(0)[0] == model


def test_card_distinguishes_pending_from_unavailable_fit(qt_app):
    card = ModelCard(_m())
    card.set_scoring_pending()
    assert card._summary.text() == "Scoring hardware match..."
    assert card._fit_panel.isVisible() is False

    card.set_score_unavailable("No compatible GGUF fit available.")
    assert card._summary.text() == "No compatible GGUF fit available."
    assert card._fit_panel.isVisible() is False

    card.set_detail_error("Could not load GGUF file metadata.")
    assert card._summary.text() == "Could not load GGUF file metadata."
    assert card._fit_panel.isVisible() is False
