from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from app.lab.services.huggingface import HFModel, HFModelFile
from app.ui.components.model_card import ModelCard


def _m(name="x-gguf", tags=None, files=None):
    return HFModel(
        id=f"a/{name}",
        author="a",
        name=name,
        downloads=1,
        likes=1,
        tags=tags or [],
        files=files or [],
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
    spy = QSignalSpy(card.open_hf_clicked)
    card._hf_link.click()
    assert spy.count() == 1
    assert spy.at(0)[0] == model.id


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
    card.show()
    qt_app.processEvents()
    card.set_scoring_pending()
    assert card._summary.text() == "Scoring hardware match..."
    assert card._summary.isVisible() is True
    assert card._fit_panel.isVisible() is False

    card.set_score_unavailable("No compatible GGUF fit available.")
    assert card._summary.text() == "No compatible GGUF fit available."
    assert card._summary.isVisible() is True
    assert card._fit_panel.isVisible() is False

    card.set_detail_error("Could not load GGUF file metadata.")
    assert card._summary.text() == "Could not load GGUF file metadata."
    assert card._summary.isVisible() is True
    assert card._fit_panel.isVisible() is False


def test_card_renders_model_information_rows(qt_app):
    card = ModelCard(
        _m(
            name="Qwen2.5-Coder-7B-Instruct-GGUF",
            tags=["gguf", "7b", "text-generation"],
            files=[HFModelFile("nested/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
        )
    )

    assert card._info_values["File"].text() == "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"
    assert card._info_values["Format"].text() == "GGUF"
    assert card._info_values["Quantization"].text() == "Q4_K_M"
    assert card._info_values["Arch"].text() == "Qwen"
    assert card._info_values["Domain"].text() == "Coding"
    assert "4." in card._info_values["Size on disk"].text()
    assert card._meta_values["Author"].text() == "a"
    assert card._meta_values["Likes"].text() == "1"
    assert card._meta_values["Downloads"].text() == "1"
    assert card._info_pills["Format"].sizeHint().width() > card._info_values["Format"].sizeHint().width()
    assert card._info_pills["Domain"].sizeHint().width() > card._info_values["Domain"].sizeHint().width()


def test_card_information_panel_can_collapse(qt_app):
    card = ModelCard(_m(files=[HFModelFile("x.gguf", 100, "Q4_K_M")]))
    card.show()

    assert card._info_body.isVisible() is False
    assert card._info_toggle.text() == "Show"

    card._info_toggle.click()
    qt_app.processEvents()

    assert card._info_body.isVisible() is True
    assert card._info_toggle.text() == "Hide"

    card._info_toggle.click()
    qt_app.processEvents()

    assert card._info_body.isVisible() is False
    assert card._info_toggle.text() == "Show"


def test_card_hides_summary_when_best_match_is_rendered(qt_app):
    card = ModelCard(_m())
    card.show()
    qt_app.processEvents()
    card.set_instance_scores([
        {"iid": 12, "score": 91, "fit": "Perfect Fit", "level": "ok", "best_quant": "Q4_K_M"}
    ])

    assert card._fit_panel.isVisible() is True
    assert card._summary.isVisible() is False
