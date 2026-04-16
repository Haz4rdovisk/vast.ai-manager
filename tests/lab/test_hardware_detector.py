from app.lab.services.hardware import pick_best_backend
from app.lab.state.models import GPUInfo


def test_pick_best_backend_cuda():
    gpus = [GPUInfo("RTX 4090", 24.0, "555", True)]
    assert pick_best_backend("Windows", gpus) == "cuda"


def test_pick_best_backend_cpu_when_no_gpu():
    assert pick_best_backend("Windows", []) == "cpu"


def test_pick_best_backend_metal_on_mac():
    assert pick_best_backend("Darwin", []) == "metal"


def test_pick_best_backend_cuda_wins_on_multi_gpu():
    gpus = [GPUInfo("RTX 3090", 24.0, "555", True),
            GPUInfo("RTX 4090", 24.0, "555", True)]
    assert pick_best_backend("Linux", gpus) == "cuda"
