from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock, Thread

from . import db
from .db import VersionRow
from .runtime import RolloutStatus, RuntimeState


@dataclass
class RolloutPlan:
    service: str
    to_version: str
    canary_weight: int
    step_percent: int
    step_interval_s: int
    auto: bool
    max_wait_s: int
    steps: list[int]
    step_index: int = 0


class RolloutManager:
    """Coordinates canary/blue-green style rollouts by adjusting version weights."""

    def __init__(self, runtime: RuntimeState):
        self.runtime = runtime
        self._lock = Lock()
        self._plans: dict[str, RolloutPlan] = {}

    def start_rollout(
        self,
        service: str,
        new_version: str,
        image: str,
        internal_port: int,
        health_path: str,
        replicas: int,
        canary_weight: int = 10,
        step_percent: int = 25,
        step_interval_s: int = 15,
        auto: bool = True,
        max_wait_s: int = 120,
    ) -> str:
        canary_weight = max(0, min(100, int(canary_weight)))
        step_percent = max(1, min(100, int(step_percent)))
        step_interval_s = max(1, int(step_interval_s))
        replicas = max(1, int(replicas))

        # Candidate version
        v_new = db.upsert_version(
            service_name=service,
            version=new_version,
            image=image,
            internal_port=internal_port,
            health_path=health_path,
            desired_replicas=replicas,
            route_weight=canary_weight,
            state="candidate",
        )

        # Reduce active weights so total is ~100
        active = [v for v in db.list_versions(service) if v.state == "active" and v.id != v_new.id]
        self._rebalance_old_versions(active, target_total=100 - canary_weight)

        rollout_id = secrets.token_hex(6)
        st = RolloutStatus(
            id=rollout_id,
            service=service,
            to_version=new_version,
            state="running" if auto else "paused",
            message=f"Created candidate {new_version} with weight {canary_weight}%",
        )
        self.runtime.upsert_rollout(st)
        db.log_event("INFO", st.message, service_name=service, version=new_version)

        steps = list(range(canary_weight, 101, step_percent))
        if steps[-1] != 100:
            steps.append(100)

        plan = RolloutPlan(
            service=service,
            to_version=new_version,
            canary_weight=canary_weight,
            step_percent=step_percent,
            step_interval_s=step_interval_s,
            auto=auto,
            max_wait_s=max_wait_s,
            steps=steps,
        )

        with self._lock:
            self._plans[rollout_id] = plan

        if auto:
            Thread(target=self._run_auto, args=(rollout_id,), daemon=True).start()

        return rollout_id

    def continue_rollout(self, rollout_id: str) -> RolloutStatus:
        with self._lock:
            plan = self._plans.get(rollout_id)
        if not plan:
            raise KeyError("unknown rollout")
        st = self.runtime.get_rollout(rollout_id)
        if not st:
            raise KeyError("unknown rollout")

        if st.state in {"done", "failed"}:
            return st

        # Perform one step
        ok = self._wait_candidate_healthy(plan)
        if not ok:
            st.state = "failed"
            st.message = "Candidate did not become healthy in time"
            self.runtime.upsert_rollout(st)
            db.log_event("ERROR", st.message, service_name=plan.service, version=plan.to_version)
            return st

        next_idx = min(plan.step_index + 1, len(plan.steps) - 1)
        plan.step_index = next_idx
        weight = plan.steps[plan.step_index]
        self._apply_weight(plan.service, plan.to_version, weight)
        st.state = "paused" if plan.step_index < len(plan.steps) - 1 else "done"
        st.message = f"Applied weight {weight}%." if st.state != "done" else "Rollout completed."
        self.runtime.upsert_rollout(st)
        db.log_event("INFO", st.message, service_name=plan.service, version=plan.to_version)
        if st.state == "done":
            self._finalize(plan)
        return st

    def _run_auto(self, rollout_id: str) -> None:
        st = self.runtime.get_rollout(rollout_id)
        with self._lock:
            plan = self._plans.get(rollout_id)
        if not st or not plan:
            return

        ok = self._wait_candidate_healthy(plan)
        if not ok:
            st.state = "failed"
            st.message = "Candidate did not become healthy in time"
            self.runtime.upsert_rollout(st)
            db.log_event("ERROR", st.message, service_name=plan.service, version=plan.to_version)
            return

        # Start from current canary weight
        for idx, weight in enumerate(plan.steps):
            plan.step_index = idx
            self._apply_weight(plan.service, plan.to_version, weight)
            st.state = "running"
            st.message = f"Applied weight {weight}%"
            self.runtime.upsert_rollout(st)
            db.log_event("INFO", st.message, service_name=plan.service, version=plan.to_version)
            if weight >= 100:
                st.state = "done"
                st.message = "Rollout completed."
                self.runtime.upsert_rollout(st)
                db.log_event("INFO", st.message, service_name=plan.service, version=plan.to_version)
                self._finalize(plan)
                return
            time.sleep(plan.step_interval_s)

    def _wait_candidate_healthy(self, plan: RolloutPlan) -> bool:
        # Poll DB for candidate instances marked up.
        t0 = time.time()
        while time.time() - t0 < plan.max_wait_s:
            v = db.get_version(plan.service, plan.to_version)
            if not v:
                return False
            inst = db.list_instances(v.id)
            if inst and all(i.status == "up" for i in inst) and len(inst) >= v.desired_replicas:
                return True
            time.sleep(2)
        return False

    def _rebalance_old_versions(self, old_versions: list[VersionRow], target_total: int) -> None:
        target_total = max(0, min(100, int(target_total)))
        if not old_versions:
            return
        if len(old_versions) == 1:
            db.set_version_weight(old_versions[0].id, target_total)
            return
        # Proportional scaling based on current weights.
        cur_total = sum(max(0, v.route_weight) for v in old_versions) or 1
        assigned = 0
        for i, v in enumerate(old_versions):
            if i == len(old_versions) - 1:
                w = max(0, target_total - assigned)
            else:
                w = int(round(target_total * max(0, v.route_weight) / cur_total))
                w = max(0, min(target_total, w))
                assigned += w
            db.set_version_weight(v.id, w)

    def _apply_weight(self, service: str, to_version: str, new_weight: int) -> None:
        new_weight = max(0, min(100, int(new_weight)))
        v_new = db.get_version(service, to_version)
        if not v_new:
            return
        db.set_version_weight(v_new.id, new_weight)

        old = [v for v in db.list_versions(service) if v.state == "active" and v.id != v_new.id]
        self._rebalance_old_versions(old, target_total=100 - new_weight)

    def _finalize(self, plan: RolloutPlan) -> None:
        # Mark candidate active, retire old, scale old down.
        v_new = db.get_version(plan.service, plan.to_version)
        if not v_new:
            return
        db.set_version_state(v_new.id, "active")
        for v in db.list_versions(plan.service):
            if v.id == v_new.id:
                continue
            if v.state == "active":
                db.set_version_state(v.id, "retired")
                db.set_version_weight(v.id, 0)
                db.set_version_replicas(v.id, 0)
