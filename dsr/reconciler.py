from __future__ import annotations

import time
from threading import Thread

from . import db
from .db import VersionRow
from .docker_ops import ContainerRef, container_http_base, create_service_container, docker_available, remove_container, container_is_running
from .health import check_health
from .runtime import RouteTarget, RuntimeState
from .settings import settings
from .alerts import send_email


class Reconciler:
    """Continuously reconciles desired state with actual state."""

    def __init__(self, runtime: RuntimeState, fail_threshold: int = 2):
        self.runtime = runtime
        self.fail_threshold = max(1, int(fail_threshold))
        self._stop = False
        self._thr: Thread | None = None

    def start(self) -> None:
        if self._thr and self._thr.is_alive():
            return
        self._thr = Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self) -> None:
        self._stop = True

    def _loop(self) -> None:
        db.log_event("INFO", "Reconciler started")
        while not self._stop:
            try:
                self._tick()
            except Exception as e:
                db.log_event("ERROR", f"Reconciler tick failed: {type(e).__name__}: {e}")
            time.sleep(max(1, settings.poll_interval_s))

    def _tick(self) -> None:
        versions = [v for v in db.list_versions() if v.state in {"active", "candidate"}]
        for v in versions:
            self._ensure_replicas(v)
        for v in versions:
            self._health_and_self_heal(v)
        self._rebuild_routing(versions)

    def _ensure_replicas(self, v: VersionRow) -> None:
        """Start/replace containers so replicas == desired_replicas."""
        if not docker_available():
            return

        instances = db.list_instances(v.id)

        running_instances = [i for i in instances if container_is_running(i.container_id)]

        # Scale down if we have more than desired.
        extra = len(running_instances) - v.desired_replicas
        if extra > 0:
            # Remove the newest extras (by id order).
            for i in list(reversed(running_instances))[:extra]:
                remove_container(i.container_id, force=True)
                db.delete_instance(i.container_id)

        # Remove records for containers that disappeared.
        for i in instances:
            if not container_is_running(i.container_id):
                db.delete_instance(i.container_id)

        missing = v.desired_replicas - len(running_instances)
        for _ in range(max(0, missing)):
            ref = create_service_container(
                service=self._service_name(v.service_id),
                version=v.version,
                image=v.image,
                internal_port=v.internal_port,
            )
            db.insert_instance(v.id, ref.id, ref.name, status="starting")

    def _service_name(self, service_id: int) -> str:
        # small helper: since versions were listed already, this avoids a join for each container.
        # SQLite is fast here; keep it simple.
        for s in db.list_services():
            if s.id == service_id:
                return s.name
        return str(service_id)

    def _health_and_self_heal(self, v: VersionRow) -> None:
        service_name = self._service_name(v.service_id)
        for inst in db.list_instances(v.id):
            base = container_http_base(inst.container_name, v.internal_port)
            url = f"{base}{v.health_path}"
            ok, msg, latency = check_health(url)

            db.update_instance_health(inst.container_id, "up" if ok else "down", latency)
            prev, fail_cnt = self.runtime.mark_health(inst.container_id, ok)

            if prev is None:
                # first time seeing it
                pass
            elif prev and not ok:
                db.log_event("WARN", f"Instance became unhealthy: {msg}", service_name=service_name, version=v.version)
                self._maybe_email(service_name, v.version, inst.container_name, ok, msg)
            elif (prev is False) and ok:
                db.log_event("INFO", "Instance recovered", service_name=service_name, version=v.version)
                self._maybe_email(service_name, v.version, inst.container_name, ok, "Recovered")

            if not ok and fail_cnt >= self.fail_threshold:
                # Self-heal: replace the container.
                db.log_event(
                    "ERROR",
                    f"Self-healing: restarting container after {fail_cnt} failed checks ({msg})",
                    service_name=service_name,
                    version=v.version,
                )
                db.bump_restart_count(inst.container_id)
                remove_container(inst.container_id, force=True)
                db.delete_instance(inst.container_id)
                ref = create_service_container(
                    service=service_name,
                    version=v.version,
                    image=v.image,
                    internal_port=v.internal_port,
                )
                db.insert_instance(v.id, ref.id, ref.name, status="starting")

    def _maybe_email(self, service: str, version: str, instance_name: str, ok: bool, msg: str) -> None:
        if not settings.enable_email:
            return
        subject = f"{'✅ RECOVERED' if ok else '🚨 DOWN'}: {service} {version} ({instance_name})"
        body = f"Service: {service}\nVersion: {version}\nInstance: {instance_name}\nStatus: {'UP' if ok else 'DOWN'}\nDetail: {msg}"
        send_email(subject, body)

    def _rebuild_routing(self, versions: list[VersionRow]) -> None:
        # Build per-service weighted target list from healthy instances.
        # Gateway will do weighted selection across versions, then RR across instances.
        service_names = {v.service_id: self._service_name(v.service_id) for v in versions}
        by_service: dict[str, list[RouteTarget]] = {service_names[sid]: [] for sid in service_names}

        for v in versions:
            if v.route_weight <= 0:
                continue
            service = service_names.get(v.service_id, str(v.service_id))
            healthy_instances: list[RouteTarget] = []
            for inst in db.list_instances(v.id):
                if inst.status != "up":
                    continue
                base = container_http_base(inst.container_name, v.internal_port)
                healthy_instances.append(
                    RouteTarget(service=service, version=v.version, base_url=base, weight=v.route_weight, latency_ms=inst.last_latency_ms)
                )
            if not healthy_instances:
                continue
            by_service.setdefault(service, []).extend(healthy_instances)

        for service, targets in by_service.items():
            self.runtime.set_targets(service, targets)
