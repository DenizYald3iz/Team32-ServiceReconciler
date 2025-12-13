from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .settings import settings


def utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_db_path() -> str:
    """Return a file path usable by sqlite.

    Why this exists:
    - On many systems, if a bind-mounted *file* path does not exist,
      Docker creates a *directory* at that location. If we then try to
      open SQLite on that path, sqlite fails with "unable to open database file".
    - To make the project resilient, if the configured path is a directory,
      we place the DB file inside it.
    """

    p = os.path.abspath(settings.db_path)

    # If the path exists and is a directory, store the DB file within it.
    if os.path.isdir(p):
        p = os.path.join(p, "dsr.db")

    # Ensure parent directory exists.
    parent = os.path.dirname(p)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    return p


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_resolve_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS services (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              service_id INTEGER NOT NULL,
              version TEXT NOT NULL,
              image TEXT NOT NULL,
              internal_port INTEGER NOT NULL,
              health_path TEXT NOT NULL,
              desired_replicas INTEGER NOT NULL,
              route_weight INTEGER NOT NULL,
              state TEXT NOT NULL, -- active|candidate|retired
              created_at TEXT NOT NULL,
              UNIQUE(service_id, version),
              FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS instances (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              version_id INTEGER NOT NULL,
              container_id TEXT NOT NULL,
              container_name TEXT NOT NULL,
              status TEXT NOT NULL, -- starting|up|down
              last_health_ts TEXT,
              last_latency_ms REAL,
              restart_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES versions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              level TEXT NOT NULL,
              service_name TEXT,
              version TEXT,
              message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_instances_version_id ON instances(version_id);
            """
        )


def log_event(level: str, message: str, service_name: str | None = None, version: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (ts, level, service_name, version, message) VALUES (?, ?, ?, ?, ?)",
            (utc_now(), level.upper(), service_name, version, message),
        )


@dataclass(frozen=True)
class ServiceRow:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class VersionRow:
    id: int
    service_id: int
    version: str
    image: str
    internal_port: int
    health_path: str
    desired_replicas: int
    route_weight: int
    state: str
    created_at: str


@dataclass(frozen=True)
class InstanceRow:
    id: int
    version_id: int
    container_id: str
    container_name: str
    status: str
    last_health_ts: str | None
    last_latency_ms: float | None
    restart_count: int
    created_at: str


def _rows_to_dataclass(rows: Iterable[sqlite3.Row], cls: Any) -> list[Any]:
    out: list[Any] = []
    for r in rows:
        out.append(cls(**dict(r)))
    return out


def get_or_create_service(name: str) -> ServiceRow:
    with connect() as conn:
        cur = conn.execute("SELECT * FROM services WHERE name=?", (name,))
        row = cur.fetchone()
        if row:
            return ServiceRow(**dict(row))
        conn.execute("INSERT INTO services (name, created_at) VALUES (?, ?)", (name, utc_now()))
        cur = conn.execute("SELECT * FROM services WHERE name=?", (name,))
        return ServiceRow(**dict(cur.fetchone()))


def upsert_version(
    service_name: str,
    version: str,
    image: str,
    internal_port: int,
    health_path: str,
    desired_replicas: int,
    route_weight: int,
    state: str,
) -> VersionRow:
    svc = get_or_create_service(service_name)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO versions (service_id, version, image, internal_port, health_path, desired_replicas, route_weight, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id, version) DO UPDATE SET
              image=excluded.image,
              internal_port=excluded.internal_port,
              health_path=excluded.health_path,
              desired_replicas=excluded.desired_replicas,
              route_weight=excluded.route_weight,
              state=excluded.state
            """,
            (
                svc.id,
                version,
                image,
                internal_port,
                health_path,
                desired_replicas,
                route_weight,
                state,
                utc_now(),
            ),
        )
        cur = conn.execute("SELECT * FROM versions WHERE service_id=? AND version=?", (svc.id, version))
        return VersionRow(**dict(cur.fetchone()))


def list_services() -> list[ServiceRow]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM services ORDER BY name").fetchall()
        return _rows_to_dataclass(rows, ServiceRow)


def list_versions(service_name: str | None = None) -> list[VersionRow]:
    with connect() as conn:
        if service_name:
            cur = conn.execute(
                """
                SELECT v.* FROM versions v
                JOIN services s ON s.id = v.service_id
                WHERE s.name=?
                ORDER BY v.created_at DESC
                """,
                (service_name,),
            )
        else:
            cur = conn.execute(
                """
                SELECT v.* FROM versions v
                JOIN services s ON s.id = v.service_id
                ORDER BY s.name, v.created_at DESC
                """
            )
        return _rows_to_dataclass(cur.fetchall(), VersionRow)


def get_version(service_name: str, version: str) -> VersionRow | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT v.* FROM versions v
            JOIN services s ON s.id = v.service_id
            WHERE s.name=? AND v.version=?
            """,
            (service_name, version),
        ).fetchone()
        return VersionRow(**dict(row)) if row else None


def list_instances(version_id: int) -> list[InstanceRow]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM instances WHERE version_id=? ORDER BY id", (version_id,)).fetchall()
        return _rows_to_dataclass(rows, InstanceRow)


def insert_instance(version_id: int, container_id: str, container_name: str, status: str) -> InstanceRow:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO instances (version_id, container_id, container_name, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (version_id, container_id, container_name, status, utc_now()),
        )
        row = conn.execute("SELECT * FROM instances WHERE container_id=?", (container_id,)).fetchone()
        return InstanceRow(**dict(row))


def update_instance_health(container_id: str, status: str, latency_ms: float | None) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE instances
            SET status=?, last_health_ts=?, last_latency_ms=?
            WHERE container_id=?
            """,
            (status, utc_now(), latency_ms, container_id),
        )


def bump_restart_count(container_id: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE instances
            SET restart_count=restart_count+1
            WHERE container_id=?
            """,
            (container_id,),
        )


def delete_instance(container_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM instances WHERE container_id=?", (container_id,))


def set_version_state(version_id: int, state: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET state=? WHERE id=?", (state, version_id))


def set_version_weight(version_id: int, weight: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET route_weight=? WHERE id=?", (weight, version_id))


def set_version_replicas(version_id: int, replicas: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET desired_replicas=? WHERE id=?", (replicas, version_id))


def latest_events(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
