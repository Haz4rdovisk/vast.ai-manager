from app.lab.services.diagnostics import ServerDiagnostic, classify_server_log


def test_classify_oom():
    log = "CUDA error: out of memory\n..."
    diagnostic = classify_server_log(log)
    assert diagnostic is not None
    assert isinstance(diagnostic, ServerDiagnostic)
    assert diagnostic.code == "vram_oom"
    assert "GPU layers" in diagnostic.fix_hint


def test_classify_model_not_found():
    log = "error: failed to open /workspace/missing.gguf: No such file or directory"
    diagnostic = classify_server_log(log)
    assert diagnostic is not None
    assert diagnostic.code == "model_missing"
    assert "path" in diagnostic.fix_hint.lower()


def test_classify_cuda_mismatch():
    log = "CUDA driver version is insufficient for CUDA runtime version"
    diagnostic = classify_server_log(log)
    assert diagnostic is not None
    assert diagnostic.code == "cuda_mismatch"


def test_classify_port_in_use():
    log = "bind: Address already in use"
    diagnostic = classify_server_log(log)
    assert diagnostic is not None
    assert diagnostic.code == "port_busy"


def test_classify_unknown_returns_none_on_clean_log():
    log = "llama_new_context_with_model: compute buffer total size = ..."
    assert classify_server_log(log) is None


def test_diagnostic_banner_shows_fix(qt_app):
    from app.lab.services.diagnostics import ServerDiagnostic
    from app.ui.components.diagnostic_banner import DiagnosticBanner

    banner = DiagnosticBanner()
    banner.set_diagnostic(
        ServerDiagnostic(
            code="vram_oom",
            title="GPU out of memory",
            detail="CUDA error: out of memory",
            fix_hint="Lower GPU layers.",
            fix_action="lower_ngl",
        )
    )
    assert "out of memory" in banner.title_text()
    assert banner.fix_button_visible()
    assert banner.is_visible_hint() is True
