from app.lab.services.nvidia import parse_nvidia_smi_csv


def test_parse_single_gpu():
    csv = "NVIDIA GeForce RTX 4090, 24564, 555.85, 8.9"
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 1
    g = gpus[0]
    assert g.name == "NVIDIA GeForce RTX 4090"
    assert g.vram_total_gb == 24564 / 1024
    assert g.driver == "555.85"
    assert g.cuda_capable is True


def test_parse_multi_gpu():
    csv = (
        "NVIDIA GeForce RTX 4090, 24564, 555.85, 8.9\n"
        "NVIDIA GeForce RTX 3090, 24576, 555.85, 8.6\n"
    )
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 2
    assert gpus[1].name == "NVIDIA GeForce RTX 3090"


def test_parse_empty_returns_empty():
    assert parse_nvidia_smi_csv("") == []
    assert parse_nvidia_smi_csv("\n\n  \n") == []


def test_parse_malformed_row_skipped():
    csv = "NVIDIA RTX 3080, 10240\nNVIDIA RTX 4090, 24564, 555.85, 8.9"
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA RTX 4090"
