from app.lab.state.store import LabStore
from app.lab.state.models import HardwareSpec, BenchmarkResult


def test_store_emits_on_hardware_set():
    store = LabStore()
    received = []
    store.hardware_changed.connect(lambda s: received.append(s))
    spec = HardwareSpec(cpu_name="Ryzen 9", ram_total_gb=64.0)
    store.set_hardware(spec)
    assert len(received) == 1
    assert received[0].cpu_name == "Ryzen 9"


def test_store_benchmarks_accumulate():
    store = LabStore()
    store.add_benchmark(BenchmarkResult("a", 1.0, 10.0, 100.0, 20.0))
    store.add_benchmark(BenchmarkResult("b", 2.0, 15.0, 80.0, 25.0))
    assert len(store.benchmarks) == 2
    assert store.benchmarks[-1].model_name == "b"


def test_store_busy_flag():
    store = LabStore()
    assert not store.is_busy("download")
    store.set_busy("download", True)
    assert store.is_busy("download")
