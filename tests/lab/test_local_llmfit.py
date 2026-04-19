from app.lab.services.local_llmfit import LocalLLMFit


def test_is_installed_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert LocalLLMFit().is_installed() is False


def test_is_installed_true_when_binary_present(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "C:/tools/llmfit.exe")
    assert LocalLLMFit().is_installed() is True


def test_install_commands_on_windows():
    service = LocalLLMFit()
    commands = service.install_commands()
    assert isinstance(commands, list)
    joined = " ".join(" ".join(command) for command in commands)
    assert "llmfit" in joined
