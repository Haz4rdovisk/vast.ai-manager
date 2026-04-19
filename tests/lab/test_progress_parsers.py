from app.lab.services.progress_parsers import (
    BuildEvent,
    WgetEvent,
    parse_cmake_build_stage,
    parse_wget_progress,
)


def test_wget_progress_extracts_percent_and_speed():
    line = "     42300K .......... .......... .......... .......... ..........  7% 14.2M 8s"
    ev = parse_wget_progress(line)
    assert ev is not None
    assert isinstance(ev, WgetEvent)
    assert ev.percent == 7
    assert ev.speed == "14.2M"


def test_wget_progress_ignores_noise():
    assert parse_wget_progress("Downloading foo.gguf from HuggingFace...") is None
    assert parse_wget_progress("") is None


def test_cmake_build_stage_apt():
    ev = parse_cmake_build_stage("Reading package lists...")
    assert ev == BuildEvent(stage="apt", detail="Reading package lists...")


def test_cmake_build_stage_clone():
    ev = parse_cmake_build_stage("Cloning into '/opt/llama.cpp'...")
    assert ev == BuildEvent(stage="clone", detail="Cloning into '/opt/llama.cpp'...")


def test_cmake_build_stage_cmake_configure():
    ev = parse_cmake_build_stage("-- Configuring done (2.3s)")
    assert ev == BuildEvent(stage="cmake", detail="-- Configuring done (2.3s)")


def test_cmake_build_stage_build_percent():
    ev = parse_cmake_build_stage("[ 42%] Building CXX object common/CMakeFiles/common.dir/common.cpp.o")
    assert ev.stage == "build"
    assert ev.percent == 42


def test_cmake_build_stage_done():
    ev = parse_cmake_build_stage("INSTALL_LLAMACPP_DONE")
    assert ev == BuildEvent(stage="done", detail="INSTALL_LLAMACPP_DONE")
