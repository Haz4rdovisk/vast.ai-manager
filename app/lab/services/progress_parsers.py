"""Pure-function parsers for streamed remote output."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class WgetEvent:
    percent: int
    speed: str = ""


@dataclass
class DownloadProgressEvent:
    percent: int
    bytes_downloaded: int = 0
    bytes_total: int = 0
    speed: str = ""


@dataclass
class BuildEvent:
    stage: str
    detail: str = ""
    percent: int | None = None


_WGET_RE = re.compile(r"(\d+)%\s+(\S+)")
_CMAKE_PCT_RE = re.compile(r"\[\s*(\d+)%\]")
_REMOTE_DOWNLOAD_RE = re.compile(
    r"^DOWNLOAD_PROGRESS\|(\d+)\|(\d+)\|(\d+)\|(.*)$"
)


def parse_wget_progress(line: str) -> WgetEvent | None:
    if not line or "%" not in line:
        return None

    match = _WGET_RE.search(line)
    if not match:
        return None

    percent = int(match.group(1))
    if not 0 <= percent <= 100:
        return None

    return WgetEvent(percent=percent, speed=match.group(2))


def parse_download_progress(line: str) -> DownloadProgressEvent | None:
    if not line:
        return None

    match = _REMOTE_DOWNLOAD_RE.match(line.strip())
    if not match:
        return None

    percent = int(match.group(1))
    if not 0 <= percent <= 100:
        return None

    return DownloadProgressEvent(
        percent=percent,
        bytes_downloaded=int(match.group(2) or 0),
        bytes_total=int(match.group(3) or 0),
        speed=match.group(4).strip(),
    )


def parse_cmake_build_stage(line: str) -> BuildEvent:
    if not line:
        return BuildEvent(stage="unknown")

    if "INSTALL_LLAMACPP_DONE" in line or "LLAMACPP_ALREADY_UP_TO_DATE" in line:
        return BuildEvent(stage="done", detail=line)
    if line.startswith("Reading package lists") or line.startswith("Building dependency tree"):
        return BuildEvent(stage="apt", detail=line)
    if line.startswith("Cloning into"):
        return BuildEvent(stage="clone", detail=line)
    if line.startswith("-- "):
        return BuildEvent(stage="cmake", detail=line)

    match = _CMAKE_PCT_RE.search(line)
    if match:
        return BuildEvent(stage="build", detail=line, percent=int(match.group(1)))

    return BuildEvent(stage="unknown", detail=line)
