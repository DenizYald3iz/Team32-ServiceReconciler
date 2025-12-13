from __future__ import annotations

import argparse
import json
import sys

import requests


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Dynamic Service Reconciler CLI")
    p.add_argument("--api", default="http://localhost:8000", help="API base URL")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_svc = sub.add_parser("services", help="List services")

    s_ev = sub.add_parser("events", help="Show events")
    s_ev.add_argument("--limit", type=int, default=20)

    s_reg = sub.add_parser("register", help="Register/update a service version")
    s_reg.add_argument("--service", required=True)
    s_reg.add_argument("--version", required=True)
    s_reg.add_argument("--image", required=True)
    s_reg.add_argument("--internal-port", type=int, required=True)
    s_reg.add_argument("--health-path", default="/health")
    s_reg.add_argument("--replicas", type=int, default=1)
    s_reg.add_argument("--weight", type=int, default=100)
    s_reg.add_argument("--state", default="active")

    s_roll = sub.add_parser("rollout", help="Start a rollout")
    s_roll.add_argument("--service", required=True)
    s_roll.add_argument("--to-version", required=True)
    s_roll.add_argument("--image", required=True)
    s_roll.add_argument("--internal-port", type=int, required=True)
    s_roll.add_argument("--health-path", default="/health")
    s_roll.add_argument("--replicas", type=int, default=1)
    s_roll.add_argument("--canary-weight", type=int, default=10)
    s_roll.add_argument("--step-percent", type=int, default=25)
    s_roll.add_argument("--step-interval-s", type=int, default=15)
    s_roll.add_argument("--max-wait-s", type=int, default=120, help="Max seconds to wait for candidate to be healthy")

    mode = s_roll.add_mutually_exclusive_group()
    mode.add_argument("--auto", action="store_true", help="Run rollout automatically (default)")
    mode.add_argument("--manual", action="store_true", help="Pause after each step; advance with /rollouts/<id>/continue")

    args = p.parse_args(argv)

    base = args.api.rstrip("/")

    if args.cmd == "services":
        _print(requests.get(f"{base}/services", timeout=10).json())
        return 0

    if args.cmd == "events":
        _print(requests.get(f"{base}/events", params={"limit": args.limit}, timeout=10).json())
        return 0

    if args.cmd == "register":
        payload = {
            "service": args.service,
            "version": args.version,
            "image": args.image,
            "internal_port": args.internal_port,
            "health_path": args.health_path,
            "replicas": args.replicas,
            "weight": args.weight,
            "state": args.state,
        }
        r = requests.post(f"{base}/services", json=payload, timeout=30)
        _print(r.json())
        return 0 if r.ok else 1

    if args.cmd == "rollout":
        # Default: auto rollout unless --manual is specified.
        auto = not args.manual
        payload = {
            "to_version": args.to_version,
            "image": args.image,
            "internal_port": args.internal_port,
            "health_path": args.health_path,
            "replicas": args.replicas,
            "canary_weight": args.canary_weight,
            "step_percent": args.step_percent,
            "step_interval_s": args.step_interval_s,
            "auto": auto,
            "max_wait_s": args.max_wait_s,
        }
        r = requests.post(f"{base}/services/{args.service}/rollout", json=payload, timeout=30)
        _print(r.json())
        return 0 if r.ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
