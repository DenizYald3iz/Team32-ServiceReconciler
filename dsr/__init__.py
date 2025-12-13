"""Dynamic Service Reconciler (DSR).

Runnable, single-node orchestrator/monitor that demonstrates:
 - health monitoring
 - self-healing (restart failed containers)
 - controlled version rollouts (canary / blue-green style)
 - basic load balancing via an in-process gateway

The implementation is intentionally small so it can be audited and explained.
"""
