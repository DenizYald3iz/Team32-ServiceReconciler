from __future__ import annotations

from collections import defaultdict

from .runtime import RuntimeState, RouteTarget


class NoHealthyBackends(Exception):
    pass


def select_backend(service: str, runtime: RuntimeState) -> tuple[RouteTarget, str]:
    """Pick a backend instance for a service.

    Strategy:
      1) Select a version by weight (per-version weight)
      2) Round-robin across healthy instances within that version

    Returns (target_instance, version).
    """
    targets = runtime.get_targets(service)
    if not targets:
        raise NoHealthyBackends(f"No healthy backends for service '{service}'.")

    by_version: dict[str, list[RouteTarget]] = defaultdict(list)
    weight_by_version: dict[str, int] = {}
    for t in targets:
        by_version[t.version].append(t)
        weight_by_version.setdefault(t.version, max(0, int(t.weight)))

    versions: list[str] = []
    for ver, w in sorted(weight_by_version.items()):
        if w <= 0:
            continue
        versions.extend([ver] * w)
    if not versions:
        raise NoHealthyBackends(f"No routable versions for service '{service}'.")

    chosen_ver = versions[runtime.next_index(f"svc:{service}:ver", len(versions))]
    insts = by_version.get(chosen_ver, [])
    if not insts:
        # fall back to any version with instances
        for v, lst in by_version.items():
            if lst:
                chosen_ver = v
                insts = lst
                break
    idx = runtime.next_index(f"svc:{service}:inst:{chosen_ver}", len(insts))
    return insts[idx], chosen_ver
