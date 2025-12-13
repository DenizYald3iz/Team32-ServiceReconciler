from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock


def utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RouteTarget:
    service: str
    version: str
    base_url: str
    weight: int
    latency_ms: float | None = None


@dataclass
class RolloutStatus:
    id: str
    service: str
    to_version: str
    state: str  # running|paused|done|failed
    message: str
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


class RuntimeState:
    """In-memory state for reconciliation and routing."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.last_status: dict[str, bool] = {}  # container_id -> last healthy
        self.fail_counts: dict[str, int] = {}  # container_id -> consecutive fails
        self.routing: dict[str, list[RouteTarget]] = {}  # service -> targets
        self.rr_index: dict[str, int] = {}  # key -> idx
        self.rollouts: dict[str, RolloutStatus] = {}

    def set_targets(self, service: str, targets: list[RouteTarget]) -> None:
        with self.lock:
            self.routing[service] = targets

    def get_targets(self, service: str) -> list[RouteTarget]:
        with self.lock:
            return list(self.routing.get(service, []))

    def mark_health(self, container_id: str, healthy: bool) -> tuple[bool | None, int]:
        """Update last health and consecutive failure count.

        Returns (previous_healthy or None, current_fail_count).
        """
        with self.lock:
            prev = self.last_status.get(container_id)
            if healthy:
                self.last_status[container_id] = True
                self.fail_counts[container_id] = 0
                return prev, 0
            self.last_status[container_id] = False
            self.fail_counts[container_id] = self.fail_counts.get(container_id, 0) + 1
            return prev, self.fail_counts[container_id]

    def next_index(self, key: str, n: int) -> int:
        with self.lock:
            if n <= 0:
                return 0
            i = self.rr_index.get(key, 0) % n
            self.rr_index[key] = (i + 1) % n
            return i

    def upsert_rollout(self, st: RolloutStatus) -> None:
        with self.lock:
            st.updated_at = utc_now()
            self.rollouts[st.id] = st

    def get_rollout(self, rollout_id: str) -> RolloutStatus | None:
        with self.lock:
            return self.rollouts.get(rollout_id)

    def list_rollouts(self) -> list[RolloutStatus]:
        with self.lock:
            return list(self.rollouts.values())
