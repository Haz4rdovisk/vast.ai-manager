from PySide6.QtWidgets import QGridLayout

from app.lab.state.models import ServerParams
from app.ui.components.server_params_form import ServerParamsForm


def test_form_reflects_params(qt_app):
    params = ServerParams(
        model_path="/m.gguf",
        context_length=8192,
        gpu_layers=40,
        batch_size=256,
        ubatch_size=128,
        threads_batch=12,
        mlock=True,
        mmap=False,
        continuous_batching=False,
        context_shift=True,
        temperature=0.7,
        dynatemp_range=0.3,
        dynatemp_exp=1.4,
        top_k=64,
        top_p=0.9,
        min_p=0.06,
        xtc_probability=0.25,
        xtc_threshold=0.2,
        typical_p=0.98,
        max_tokens=2048,
        samplers="top_k,top_p,min_p,temperature",
        backend_sampling=True,
    )
    form = ServerParamsForm(["/m.gguf"])
    form.set_params(params)
    assert form.current_params().context_length == 8192
    assert form.current_params().gpu_layers == 40
    assert form.current_params().ubatch_size == 128
    assert form.current_params().threads_batch == 12
    assert form.current_params().mlock is True
    assert form.current_params().mmap is False
    assert form.current_params().continuous_batching is False
    assert form.current_params().context_shift is True
    assert form.current_params().temperature == 0.7
    assert form.current_params().dynatemp_range == 0.3
    assert form.current_params().dynatemp_exp == 1.4
    assert form.current_params().top_k == 64
    assert form.current_params().top_p == 0.9
    assert form.current_params().min_p == 0.06
    assert form.current_params().xtc_probability == 0.25
    assert form.current_params().xtc_threshold == 0.2
    assert form.current_params().typical_p == 0.98
    assert form.current_params().max_tokens == 2048
    assert form.current_params().samplers == "top_k,top_p,min_p,temperature"
    assert form.current_params().backend_sampling is True


def test_form_emits_on_change(qt_app):
    form = ServerParamsForm(["/m.gguf"])
    received: list = []
    form.changed.connect(received.append)
    form.set_params(ServerParams(model_path="/m.gguf"))
    form.ctx_spin.setValue(16384)
    assert any(params.context_length == 16384 for params in received)


def test_form_uses_two_column_grid_for_core_fields(qt_app):
    form = ServerParamsForm(["/m.gguf"])

    assert isinstance(form._core_grid, QGridLayout)

    ctx_index = form._core_grid.indexOf(form.ctx_field)
    gpu_index = form._core_grid.indexOf(form.ngl_field)
    threads_index = form._core_grid.indexOf(form.threads_field)
    batch_index = form._core_grid.indexOf(form.batch_field)

    assert form._core_grid.getItemPosition(ctx_index)[:2] == (0, 0)
    assert form._core_grid.getItemPosition(gpu_index)[:2] == (0, 1)
    assert form._core_grid.getItemPosition(threads_index)[:2] == (1, 0)
    assert form._core_grid.getItemPosition(batch_index)[:2] == (1, 1)


def test_form_uses_two_column_grid_for_secondary_fields(qt_app):
    form = ServerParamsForm(["/m.gguf"])

    assert isinstance(form._secondary_grid, QGridLayout)

    parallel_index = form._secondary_grid.indexOf(form.parallel_field)
    ubatch_index = form._secondary_grid.indexOf(form.ubatch_field)
    threads_batch_index = form._secondary_grid.indexOf(form.threads_batch_field)
    kv_index = form._secondary_grid.indexOf(form.kv_field)
    port_index = form._secondary_grid.indexOf(form.port_field)
    host_index = form._secondary_grid.indexOf(form.host_field)

    assert form._secondary_grid.getItemPosition(parallel_index) == (0, 0, 1, 1)
    assert form._secondary_grid.getItemPosition(ubatch_index) == (0, 1, 1, 1)
    assert form._secondary_grid.getItemPosition(threads_batch_index) == (1, 0, 1, 1)
    assert form._secondary_grid.getItemPosition(kv_index) == (1, 1, 1, 1)
    assert form._secondary_grid.getItemPosition(port_index) == (2, 0, 1, 1)
    assert form._secondary_grid.getItemPosition(host_index) == (2, 1, 1, 1)


def test_form_uses_two_column_grid_for_sampling_fields(qt_app):
    form = ServerParamsForm(["/m.gguf"])

    assert isinstance(form._sampling_grid, QGridLayout)

    temp_index = form._sampling_grid.indexOf(form.temperature_field)
    top_k_index = form._sampling_grid.indexOf(form.top_k_field)
    top_p_index = form._sampling_grid.indexOf(form.top_p_field)
    min_p_index = form._sampling_grid.indexOf(form.min_p_field)
    repeat_index = form._sampling_grid.indexOf(form.repeat_field)
    max_tokens_index = form._sampling_grid.indexOf(form.max_tokens_field)

    assert form._sampling_grid.getItemPosition(temp_index) == (0, 0, 1, 1)
    assert form._sampling_grid.getItemPosition(top_k_index) == (0, 1, 1, 1)
    assert form._sampling_grid.getItemPosition(top_p_index) == (1, 0, 1, 1)
    assert form._sampling_grid.getItemPosition(min_p_index) == (1, 1, 1, 1)
    assert form._sampling_grid.getItemPosition(repeat_index) == (2, 0, 1, 1)
    assert form._sampling_grid.getItemPosition(max_tokens_index) == (2, 1, 1, 1)


def test_form_uses_two_column_grid_for_toggle_fields(qt_app):
    form = ServerParamsForm(["/m.gguf"])

    assert isinstance(form._toggle_grid, QGridLayout)

    flash_index = form._toggle_grid.indexOf(form.fa_field)
    cont_batch_index = form._toggle_grid.indexOf(form.cont_batching_field)
    mlock_index = form._toggle_grid.indexOf(form.mlock_field)
    mmap_index = form._toggle_grid.indexOf(form.mmap_field)
    context_shift_index = form._toggle_grid.indexOf(form.context_shift_field)
    warmup_index = form._toggle_grid.indexOf(form.no_warmup_field)

    assert form._toggle_grid.getItemPosition(flash_index) == (0, 0, 1, 1)
    assert form._toggle_grid.getItemPosition(cont_batch_index) == (0, 1, 1, 1)
    assert form._toggle_grid.getItemPosition(mlock_index) == (1, 0, 1, 1)
    assert form._toggle_grid.getItemPosition(mmap_index) == (1, 1, 1, 1)
    assert form._toggle_grid.getItemPosition(context_shift_index) == (2, 0, 1, 1)
    assert form._toggle_grid.getItemPosition(warmup_index) == (2, 1, 1, 1)


def test_form_misc_sampling_is_collapsed_by_default_and_can_toggle(qt_app):
    form = ServerParamsForm(["/m.gguf"])

    assert form.misc_sampling_container.isHidden() is True

    form.misc_sampling_toggle.click()
    assert form.misc_sampling_container.isHidden() is False

    form.misc_sampling_toggle.click()
    assert form.misc_sampling_container.isHidden() is True
