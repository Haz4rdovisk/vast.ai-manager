from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".vastai-app" / "app.db"


class SQLiteStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hf_model_files_cache (
                    model_id TEXT PRIMARY KEY,
                    files_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS analytics_snapshots (
                    ts TEXT PRIMARY KEY,
                    balance REAL NOT NULL,
                    burn_total REAL NOT NULL,
                    burn_gpu REAL NOT NULL,
                    burn_storage REAL NOT NULL,
                    burn_network REAL NOT NULL,
                    instances_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analytics_meta (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_hf_model_cache_entry(self, model_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT model_id, files_json, fetched_at, last_error
                FROM hf_model_files_cache
                WHERE model_id = ?
                """,
                (model_id,),
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row else None

    def upsert_hf_model_cache_entry(
        self,
        model_id: str,
        files_json: str,
        fetched_at: float,
        *,
        last_error: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO hf_model_files_cache (model_id, files_json, fetched_at, last_error)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    files_json = excluded.files_json,
                    fetched_at = excluded.fetched_at,
                    last_error = excluded.last_error
                """,
                (model_id, files_json, fetched_at, last_error),
            )
            conn.commit()
        finally:
            conn.close()

    def load_analytics_payload(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT ts, balance, burn_total, burn_gpu, burn_storage, burn_network, instances_json
                FROM analytics_snapshots
                ORDER BY ts
                """
            ).fetchall()
            meta_rows = conn.execute(
                "SELECT key, value_json FROM analytics_meta"
            ).fetchall()
        finally:
            conn.close()

        entries = []
        for row in rows:
            try:
                instances = json.loads(row["instances_json"])
            except (TypeError, json.JSONDecodeError):
                instances = []
            entries.append(
                {
                    "ts": row["ts"],
                    "balance": row["balance"],
                    "burn_total": row["burn_total"],
                    "burn_gpu": row["burn_gpu"],
                    "burn_storage": row["burn_storage"],
                    "burn_network": row["burn_network"],
                    "instances": instances,
                }
            )

        meta: dict[str, Any] = {}
        for row in meta_rows:
            try:
                meta[row["key"]] = json.loads(row["value_json"])
            except (TypeError, json.JSONDecodeError):
                continue

        return {
            "entries": entries,
            "owner_key": meta.get("owner_key"),
            "last_recharge_val": meta.get("last_recharge_val", 0.0),
            "last_recharge_ts": meta.get("last_recharge_ts", 0.0),
            "billing_summary": meta.get("billing_summary", {}),
            "billing_events": meta.get("billing_events", []),
        }

    def save_analytics_payload(self, payload: dict[str, Any]) -> None:
        entries = payload.get("entries") or []
        meta_items = {
            "owner_key": payload.get("owner_key"),
            "last_recharge_val": payload.get("last_recharge_val", 0.0),
            "last_recharge_ts": payload.get("last_recharge_ts", 0.0),
            "billing_summary": payload.get("billing_summary", {}),
            "billing_events": payload.get("billing_events", []),
        }

        conn = self._connect()
        try:
            conn.execute("DELETE FROM analytics_snapshots")
            conn.execute("DELETE FROM analytics_meta")
            conn.executemany(
                """
                INSERT INTO analytics_snapshots (
                    ts, balance, burn_total, burn_gpu, burn_storage, burn_network, instances_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.get("ts", ""),
                        float(entry.get("balance", 0.0)),
                        float(entry.get("burn_total", 0.0)),
                        float(entry.get("burn_gpu", 0.0)),
                        float(entry.get("burn_storage", 0.0)),
                        float(entry.get("burn_network", 0.0)),
                        json.dumps(entry.get("instances") or [], separators=(",", ":")),
                    )
                    for entry in entries
                ],
            )
            conn.executemany(
                "INSERT INTO analytics_meta (key, value_json) VALUES (?, ?)",
                [
                    (key, json.dumps(value, separators=(",", ":")))
                    for key, value in meta_items.items()
                ],
            )
            conn.commit()
        finally:
            conn.close()
