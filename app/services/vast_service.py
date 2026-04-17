from __future__ import annotations
import json
import time
from typing import Any
from app.models import Instance, InstanceState, UserInfo


class VastAuthError(Exception):
    pass


class VastNetworkError(Exception):
    pass


def _derive_state(actual: str | None, intended: str | None) -> InstanceState:
    a = (actual or "").lower()
    i = (intended or "").lower()
    if a == "running":
        return InstanceState.RUNNING
    if a in ("exited", "stopped", "offline"):
        if i == "running":
            return InstanceState.STARTING
        return InstanceState.STOPPED
    if a in ("loading", "scheduling", "created"):
        return InstanceState.STARTING
    if i == "stopped" and a != "running":
        return InstanceState.STOPPING
    return InstanceState.UNKNOWN


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normalize_util(v: Any) -> float | None:
    """CPU/GPU util can come as a ratio (0..1) or as a percentage (0..100).
    Detect by magnitude and normalize to percent."""
    f = _to_float(v)
    if f is None:
        return None
    if f < 0:
        return None
    # Treat <=1.5 as ratio (covers small noise above 1.0); otherwise already %.
    if f <= 1.5:
        return f * 100.0
    return f


def _nested_float(raw: dict, *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        cur: Any = raw
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        val = _to_float(cur)
        if val is not None:
            return val
    return None


def parse_instance(raw: dict) -> Instance:
    gpu_ram_mb = _to_float(raw.get("gpu_ram")) or 0.0
    cpu_ram_mb = _to_float(raw.get("cpu_ram"))
    mem_usage_mb = _to_float(raw.get("mem_usage"))
    vmem_usage_mb = _to_float(raw.get("vmem_usage"))

    image = raw.get("label") or raw.get("image_uuid")

    iid = int(raw["id"])
    ssh_host = ""
    ssh_port = 0
    ports = raw.get("ports") or {}
    if "22/tcp" in ports and ports["22/tcp"]:
        ssh_host = raw.get("public_ipaddr") or ""
        ssh_port = _to_int(ports["22/tcp"][0].get("HostPort")) or 0

    if not ssh_host or not ssh_port:
        ssh_host = raw.get("ssh_host") or raw.get("public_ipaddr") or ""
        ssh_port = _to_int(raw.get("ssh_port")) or 0

    state = _derive_state(raw.get("actual_status"), raw.get("intended_status"))
    is_running = state == InstanceState.RUNNING

    # Telemetry only valid while the container is actually running.
    # Vast keeps stale last-known values on stopped/starting instances —
    # surfacing them is misleading, so we drop them.
    gpu_util = _normalize_util(raw.get("gpu_util")) if is_running else None
    gpu_temp = _to_float(raw.get("gpu_temp")) if is_running else None
    vram_usage_gb = (vmem_usage_mb / 1024.0) if (is_running and vmem_usage_mb) else None
    cpu_util = _normalize_util(raw.get("cpu_util")) if is_running else None
    ram_used_gb = (mem_usage_mb / 1024.0) if (is_running and mem_usage_mb) else None
    disk_usage_gb = _to_float(raw.get("disk_usage")) if is_running else None
    inet_down = _to_float(raw.get("inet_down")) if is_running else None
    inet_up = _to_float(raw.get("inet_up")) if is_running else None

    # Extra metadata Vast exposes; harmless if missing on a given instance.
    geo = raw.get("geolocation") or None
    country = None
    if geo and "," in geo:
        # Vast sends e.g. "São Paulo, BR" — last comma-separated part is the
        # country/region code.
        country = geo.rsplit(",", 1)[-1].strip()
    cuda_max = _to_float(raw.get("cuda_max_good"))
    pcie_gen = _to_float(raw.get("pci_gen") or raw.get("pcie_gen"))

    return Instance(
        id=iid,
        state=state,
        gpu_name=raw.get("gpu_name") or "Unknown GPU",
        num_gpus=_to_int(raw.get("num_gpus")) or 1,
        gpu_ram_gb=gpu_ram_mb / 1024.0,
        gpu_util=gpu_util,
        gpu_temp=gpu_temp,
        vram_usage_gb=vram_usage_gb,
        cpu_name=raw.get("cpu_name"),
        cpu_cores=_to_int(raw.get("cpu_cores")),
        cpu_util=cpu_util,
        ram_total_gb=(cpu_ram_mb / 1024.0) if cpu_ram_mb else None,
        ram_used_gb=ram_used_gb,
        disk_usage_gb=disk_usage_gb,
        disk_space_gb=_to_float(raw.get("disk_space")),
        inet_down_mbps=inet_down,
        inet_up_mbps=inet_up,
        image=image,
        dph=_to_float(raw.get("dph_total")) or 0.0,
        duration_seconds=_to_int(raw.get("duration")),
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        geolocation=geo,
        country=country,
        hostname=raw.get("hostname") or None,
        host_id=_to_int(raw.get("host_id")),
        machine_id=_to_int(raw.get("machine_id")),
        datacenter=raw.get("datacenter") or None,
        hosting_type=raw.get("hosting_type") or None,
        cuda_max_good=cuda_max,
        cpu_arch=raw.get("cpu_arch") or None,
        mobo_name=raw.get("mobo_name") or None,
        os_version=raw.get("os_version") or None,
        pcie_gen=pcie_gen,
        pcie_bw_gbps=_to_float(raw.get("pcie_bw")),
        disk_bw_mbps=_to_float(raw.get("disk_bw")),
        dlperf=_to_float(raw.get("dlperf")),
        total_flops=_to_float(raw.get("total_flops")),
        flops_per_dphtotal=_to_float(raw.get("flops_per_dphtotal")),
        reliability=_to_float(raw.get("reliability2") or raw.get("reliability")),
        verification=raw.get("verification") or None,
        inet_down_billed_gb=_to_float(raw.get("inet_down_billed")),
        inet_up_billed_gb=_to_float(raw.get("inet_up_billed")),
        discounted_total_per_hour=_nested_float(
            raw,
            ("discounted_total_per_hour",),
            ("discountedTotalPerHour",),
            ("instance", "discountedTotalPerHour"),
            ("search", "discountedTotalPerHour"),
        ),
        storage_cost_per_gb_month=_to_float(
            raw.get("storage_cost") or raw.get("storageCost")
        ),
        storage_total_cost=_to_float(raw.get("storage_total_cost")),
        raw=raw,
    )


def parse_user_info(raw: dict) -> UserInfo:
    return UserInfo(
        balance=_to_float(raw.get("credit")) or 0.0,
        email=raw.get("email"),
    )


def _normalize_response(raw):
    """SDK methods sometimes return strings (printed output) or dicts. Handle both."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if raw is not None else {}


def _results_from_response(raw: Any) -> list[dict]:
    data = _normalize_response(raw)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("results", "charges", "invoices"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return []


class VastService:
    """Wraps the vastai SDK. Holds api_key and exposes typed methods."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._sdk = None

    def _client(self):
        if self._sdk is None:
            try:
                from vastai import VastAI
            except ImportError as e:
                raise RuntimeError(
                    "vastai package not installed. Run: pip install vastai"
                ) from e
            self._sdk = VastAI(api_key=self.api_key)
        return self._sdk

    def _call(self, fn_name: str, **kwargs):
        sdk = self._client()
        fn = getattr(sdk, fn_name)
        try:
            return fn(**kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthori" in msg or "forbidden" in msg or "invalid api key" in msg:
                raise VastAuthError(str(e)) from e
            raise VastNetworkError(str(e)) from e

    def test_connection(self) -> UserInfo:
        raw = self._call("show_user")
        return parse_user_info(_normalize_response(raw))

    def list_instances(self) -> list[Instance]:
        raw = self._call("show_instances")
        items = _normalize_response(raw)
        if isinstance(items, dict) and "instances" in items:
            items = items["instances"]
        if not isinstance(items, list):
            return []
        parsed = []
        for i in items:
            if isinstance(i, dict) and "id" in i:
                try:
                    parsed.append(parse_instance(i))
                except (KeyError, TypeError, ValueError):
                    continue
        return parsed

    def start_instance(self, instance_id: int) -> None:
        self._call("start_instance", id=instance_id)

    def stop_instance(self, instance_id: int) -> None:
        self._call("stop_instance", id=instance_id)

    def get_user_info(self) -> UserInfo:
        return self.test_connection()

    def _fetch_billing_pages(
        self,
        *,
        charges: bool,
        start_ts: int,
        end_ts: int,
        limit: int = 100,
        max_pages: int = 20,
    ) -> list[dict]:
        """Fetch paginated billing rows through the official VastAI SDK.

        The SDK maps this to the current REST endpoints:
        - charges: GET /api/v0/charges/ with a `day` select_filter
        - invoices: GET /api/v1/invoices/ with a `when` select_filter
        """
        rows: list[dict] = []
        next_token = None
        for _ in range(max_pages):
            kwargs: dict[str, Any] = {
                "charges": charges,
                "start_date": start_ts,
                "end_date": end_ts,
                "latest_first": True,
                "limit": max(1, min(limit, 100)),
            }
            if charges:
                kwargs["format"] = "tree"
            if next_token:
                kwargs["next_token"] = next_token

            raw = self._call("show_invoices_v1", **kwargs)
            data = _normalize_response(raw)
            if isinstance(data, dict) and data.get("success") is False:
                raise VastNetworkError(str(data.get("msg") or data.get("error") or data))

            rows.extend(_results_from_response(data))
            if not isinstance(data, dict):
                break
            next_token = data.get("next_token")
            if not next_token:
                break
        return rows

    def fetch_financial_data(self, days: int = 30) -> dict:
        """Fetch invoices and charges used by Analytics.

        Live resources already flow through `show_user` and `show_instances`.
        This deep sync uses the VastAI SDK's current billing wrapper so the app
        gets itemized GPU, storage and bandwidth charges plus credit/top-up
        invoices without maintaining raw HTTP endpoint glue in the UI layer.
        """
        days = max(1, min(int(days), 90))
        end_ts = int(time.time())
        start_ts = end_ts - (days * 24 * 3600)

        charges = self._fetch_billing_pages(
            charges=True, start_ts=start_ts, end_ts=end_ts
        )
        invoices = self._fetch_billing_pages(
            charges=False, start_ts=start_ts, end_ts=end_ts
        )
        return {
            "invoices": invoices,
            "charges": charges,
            "sync": {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "days": days,
                "charge_count": len(charges),
                "invoice_count": len(invoices),
            },
        }
