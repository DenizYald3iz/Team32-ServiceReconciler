# Perfect System (Tron edition) — Plus

A tiny **desired-state orchestrator** demo inspired by *Tron* and *Kubernetes*.
You **declare Desired** (via YAML) and the **Controller reconciles Actual** until they match.

## What’s new vs baseline
- **Guided Tour** & **Help Modal** (self-explanatory UI)
- **Play Demo** button (v1 → v2 rollout → chaos → self-heal)
- **Blue/Green** and **Canary** rollouts
- **Readiness vs Liveness** probes, **exponential backoff** on restarts
- **Simulated Autoscaling** with a tiny HPA-like controller
- **Explain Mode** (friendly reasons appended to events)
- **Observability mini-charts** (ready pods / restarts)
- **Diff view**: Desired vs Actual per service
- **OpenAPI /docs** for API (Swagger UI)
- **Auth key** support for mutating endpoints (optional)

## Quick start
```bash
docker compose up --build
# UI: http://localhost:8080
# API docs: http://localhost:8080/docs
```
Try the **Play Demo** button in the header, or:
```bash
# Apply v1
curl -sS -H 'Content-Type: application/yaml' --data-binary @examples/api-v1.yaml http://localhost:8080/apply | jq
# Apply v2 (canary)
curl -sS -H 'Content-Type: application/yaml' --data-binary @examples/api-canary.yaml http://localhost:8080/apply | jq
# Chaos
curl -X POST 'http://localhost:8080/chaos/kill?service=api&count=1' | jq
```

## Mental model (30 sec)
- **Service**: desired **replicas**, **image digest**, **env**, **rollout** strategy
- **Pod**: an instance belonging to a service (simulated by the Agent)
- **Controller**: reconcile loop (every 1s) → spawn/kill/restart pods, perform rollouts, autoscale
- **Readiness**: pod is *ready* to receive traffic
- **Liveness**: pod is *alive*; failing liveness triggers restarts with backoff
- **Events**: append-only log of what happened (filterable, explainable)

## Examples
- `examples/api-v1.yaml` — baseline v1
- `examples/api-v2.yaml` — blue/green v2
- `examples/api-canary.yaml` — canary 25%→50%→100% with pauses

## Feature flags & env
- `X_API_KEY` (api+controller+agent): set to require `X-API-Key` header for mutating routes
- `TICK_MS` (controller): reconcile period (default 1000ms)

### Email alerts (optional)
If configured, the **Controller** sends an email when a service transitions:
- **DOWN**: desired replicas > 0 and **ready pods < desired replicas** (degraded counts as down)
- **UP**: ready pods back to **>= desired replicas**

Configure via env vars on the `controller` service (see `docker-compose.yml`):
- `SMTP_HOST`, `SMTP_PORT` (default `587`), `SMTP_SECURE` (default `false`, or `true` for port `465`)
- `SMTP_USER`, `SMTP_PASS` (optional)
- `EMAIL_FROM` (default `perfect-system@localhost`)
- `EMAIL_TO` (comma-separated recipients)
- `EMAIL_SUBJECT_PREFIX` (default `[Perfect System] `)
- `PUBLIC_UI_URL` (optional link in the email)

Alert behavior knobs:
- `ALERT_DOWN_CONFIRM_MS` / `ALERT_UP_CONFIRM_MS` (default `0`): require a state to persist before alerting
- `ALERT_COOLDOWN_MS` (default `0`): minimum time between emails for a service
- `ALERT_STARTUP_GRACE_MS` (default `5000`): suppress alerts right after scaling from 0 → >0

---
© for homework/demo use. Have fun on the Grid! 🛡️
