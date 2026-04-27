from app.models import Instance, InstanceState, TunnelStatus


def test_parse_instance_keeps_scheduling_status_message():
    from app.services.vast_service import parse_instance

    message = "Attempting to schedule your instance. Your GPU is currently in use."
    inst = parse_instance(
        {
            "id": 42,
            "actual_status": "scheduling",
            "intended_status": "running",
            "gpu_name": "RTX 3090",
            "status_msg": message,
        }
    )

    assert inst.state == InstanceState.STARTING
    assert inst.status_message == message


def test_action_bar_shows_scheduling_cta_with_tooltip(qt_app):
    from app.ui.views.instances.action_bar import ActionBar

    inst = Instance(
        id=42,
        state=InstanceState.STARTING,
        gpu_name="RTX 3090",
        status_message="Attempting to schedule your instance.",
        raw={"actual_status": "scheduling", "intended_status": "running"},
    )

    bar = ActionBar(inst, TunnelStatus.DISCONNECTED)

    assert bar.primary.text() == "Connect"
    assert "Attempting to schedule" in bar.primary.toolTip()
    assert bar.primary.isEnabled() is False


def test_action_bar_uses_default_scheduling_tooltip_when_api_omits_message(qt_app):
    from app.ui.views.instances.action_bar import ActionBar

    inst = Instance(
        id=42,
        state=InstanceState.STARTING,
        gpu_name="RTX 3090",
        raw={"actual_status": "scheduling", "intended_status": "running"},
    )

    bar = ActionBar(inst, TunnelStatus.DISCONNECTED)

    assert "GPU is currently in use" in bar.primary.toolTip()


def test_action_bar_detects_scheduling_from_intended_running(qt_app):
    from app.ui.views.instances.action_bar import ActionBar

    inst = Instance(
        id=42,
        state=InstanceState.STARTING,
        gpu_name="RTX 3090",
        status_message="success, running vastai/base-image_cuda-12.1.1-auto/jupyter",
        raw={"actual_status": "exited", "intended_status": "running"},
    )

    bar = ActionBar(inst, TunnelStatus.DISCONNECTED)

    assert bar.primary.text() == "Connect"
    assert "GPU is currently in use" in bar.primary.toolTip()


def test_action_bar_stop_icon_stops_scheduling_instance(qt_app):
    from app.ui.views.instances.action_bar import ActionBar

    inst = Instance(
        id=42,
        state=InstanceState.STARTING,
        gpu_name="RTX 3090",
        raw={"actual_status": "scheduling", "intended_status": "running"},
    )

    bar = ActionBar(inst, TunnelStatus.DISCONNECTED)
    seen = []
    bar.deactivate_requested.connect(lambda: seen.append(True))

    bar.btn_reboot.click()

    assert "Storage charges still apply" in bar.btn_reboot.toolTip()
    assert seen == [True]


def test_action_bar_shows_outbid_state(qt_app):
    from app.ui.views.instances.action_bar import ActionBar, is_scheduling_instance

    inst = Instance(
        id=42,
        state=InstanceState.OUTBID,
        gpu_name="RTX 4090",
        num_gpus=1,
        gpu_ram_gb=24,
        image="img",
        dph=0.5,
        raw={"actual_status": "exited", "intended_status": "running", "_is_outbid": True},
    )
    bar = ActionBar(inst, TunnelStatus.DISCONNECTED)
    assert bar.primary.text() == "Unavailable"
    assert bar.primary.isEnabled() is False
    assert "outbid" in bar.primary.toolTip().lower() or "terminated" in bar.primary.toolTip().lower()
    assert not is_scheduling_instance(inst)
