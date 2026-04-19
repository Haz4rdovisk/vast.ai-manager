from __future__ import annotations

from threading import Lock
from typing import Callable


class PortAllocator:
    """Assign unique local ports per instance id and persist mutations."""

    def __init__(
        self,
        default_port: int,
        initial_map: dict[int, int],
        persist: Callable[[dict[int, int]], None],
    ) -> None:
        self._default = default_port
        self._map: dict[int, int] = dict(initial_map)
        self._persist = persist
        self._lock = Lock()

    def get(self, instance_id: int) -> int:
        with self._lock:
            if instance_id in self._map:
                return self._map[instance_id]
            port = self._next_free_locked()
            self._map[instance_id] = port
            self._persist(dict(self._map))
            return port

    def _next_free_locked(self) -> int:
        used = set(self._map.values())
        port = self._default
        while port in used:
            port += 1
            if port > self._default + 999:
                raise RuntimeError(
                    f"Port exhaustion in [{self._default}, {self._default + 999}]"
                )
        return port

    def release(self, instance_id: int) -> None:
        with self._lock:
            if self._map.pop(instance_id, None) is not None:
                self._persist(dict(self._map))

    def compact(self, alive_ids: set[int]) -> None:
        with self._lock:
            stale = [iid for iid in self._map if iid not in alive_ids]
            for iid in stale:
                del self._map[iid]
            if stale:
                self._persist(dict(self._map))

    def snapshot(self) -> dict[int, int]:
        with self._lock:
            return dict(self._map)
