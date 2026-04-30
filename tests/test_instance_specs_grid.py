from PySide6.QtWidgets import QApplication

from app.models import Instance, InstanceState
from app.ui.views.instances.specs_grid import SpecsGrid


def _app():
    return QApplication.instance() or QApplication([])


def test_specs_grid_keeps_full_cpu_and_mobo_names(qt_app):
    _app()
    inst = Instance(
        id=35838665,
        state=InstanceState.RUNNING,
        gpu_name="RTX 4090",
        host_id=159006,
        cuda_max_good=13.0,
        total_flops=7.4,
        dlperf=3.2,
        flops_per_dphtotal=228.4,
        inet_down_mbps=159.8,
        inet_up_mbps=181.0,
        cpu_name="Xeon E5-2680 v4",
        cpu_cores=56,
        ram_total_gb=62.8,
        disk_space_gb=20.0,
        disk_bw_mbps=490.0,
        mobo_name="X99-F8D PLUS",
        pcie_gen=3.0,
        pcie_bw_gbps=11.2,
    )

    grid = SpecsGrid(inst)

    assert grid.value_text("cpu") == "Xeon E5-2680 v4"
    assert grid.value_text("mobo") == "X99-F8D PLUS"
