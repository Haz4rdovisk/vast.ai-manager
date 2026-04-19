from app.lab.state.models import ServerParams
from app.ui.components.server_params_form import ServerParamsForm


def test_form_reflects_params(qt_app):
    params = ServerParams(
        model_path="/m.gguf",
        context_length=8192,
        gpu_layers=40,
        batch_size=256,
    )
    form = ServerParamsForm(["/m.gguf"])
    form.set_params(params)
    assert form.current_params().context_length == 8192
    assert form.current_params().gpu_layers == 40


def test_form_emits_on_change(qt_app):
    form = ServerParamsForm(["/m.gguf"])
    received: list = []
    form.changed.connect(received.append)
    form.set_params(ServerParams(model_path="/m.gguf"))
    form.ctx_spin.setValue(16384)
    assert any(params.context_length == 16384 for params in received)
