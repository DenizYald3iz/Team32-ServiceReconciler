# Team32 Service Reconciler (Perfect System · Tron UI)

A small **desired-state orchestrator** demo inspired by Kubernetes:

- You declare **Desired** state (via YAML).
- A **Controller** continuously reconciles **Actual** state until they match.
- A web UI shows services/pods/events live and exposes basic API + metrics.

> Includes an optional **email alerting** feature for service UP/DOWN transitions.  
> This version also fixes the “same email sent twice” issue (see **Email alerts** + **Troubleshooting**).

---

## Architecture (3 services)

- **API** (`services/api`)  
  Serves the UI, accepts YAML specs, exposes `/state`, and pushes state updates via SSE.
- **Controller** (`services/controller`)  
  Reconcile loop: spawn/kill pods, perform rollouts, run probes, autoscale, emit events, send alerts.
- **Agent** (`services/agent`)  
  Simulates “pods” (not real containers): assigns ports, responds to probes, supports kill/drain.

State is stored in a shared JSON file (mounted volume) so API + Controller see the same cluster state.

---

## Quick start (Docker)

```bash
docker compose up --build
```

Open:
- UI: http://localhost:8080
- API docs (Swagger): http://localhost:8080/docs
- Metrics (Prometheus text): http://localhost:8080/metrics

---

## Using the system

### Apply a service spec (YAML)

```bash
curl -sS -H 'Content-Type: application/yaml'   --data-binary @examples/api-v1.yaml   http://localhost:8080/apply
```

Other examples:
- `examples/api-v1.yaml` — baseline
- `examples/api-v2.yaml` — blue/green style rollout
- `examples/api-canary.yaml` — canary rollout in steps

### Chaos (kill pods)

```bash
curl -X POST "http://localhost:8080/chaos/kill?service=api&count=1"
```

### Simulated load (for autoscaling demos)

```bash
curl -X POST "http://localhost:8080/load?service=api&cpu=80"
```

### Manual scale

```bash
curl -X POST "http://localhost:8080/scale?service=api&delta=1"
curl -X POST "http://localhost:8080/scale?service=api&delta=-1"
```

---

## Service YAML format (what `/apply` expects)

Minimum shape:

```yaml
kind: Service
metadata:
  name: api
spec:
  replicas: 3
  image: local://demo@v1
```

Supported `spec` fields (as used by the Controller/Agent simulation):
- `replicas` (number)
- `image` (string)  
  The controller uses the “digest” portion to detect version drift (e.g. `...@v2`).
- `env` (list of `{name, value}`)  
  The Agent reads env values like `HEALTHY` to simulate probe results.
- `rollout` (object)  
  - `strategy: BlueGreen | Canary`
  - for canary: `steps: [{percent: 25}, {percent: 50}, ...]` and `pauseSeconds`
- `readinessProbe` / `livenessProbe` (objects)  
  Supports `initialDelaySeconds`, `failureThreshold`, etc. (simulation).
- `autoscale` (object)  
  Supports `targetCPU`, `min`, `max` (simple HPA-like logic).

---

## API endpoints (high level)

- `GET /` — UI
- `GET /docs` — Swagger UI
- `GET /state` — current cluster state
- `GET /events` — Server-Sent Events stream of state updates
- `GET /metrics` — Prometheus-style metrics (proxied from controller)
- `POST /apply` — apply a Service YAML
- `POST /chaos/kill?service=...&count=...` — kill running pods
- `POST /load?service=...&cpu=0..100` — set simulated CPU
- `POST /scale?service=...&delta=+1|-1` — adjust desired replicas

---

## Security (optional API key)

If you set `X_API_KEY`, mutating endpoints require `X-API-Key: <value>`.

Where to set:
- `docker-compose.yml` (API / Controller / Agent)

---

## Metrics

The Controller exposes `/metrics` in Prometheus text format, including:
- ready pods / desired pods / total pods per service
- restart counters
- event counters by service and level

The API proxies this at: `http://localhost:8080/metrics`.

---

## Email alerts (optional)

When configured, the **Controller** sends an email when a service transitions:

- **DOWN**: desired replicas > 0 and **ready < desired**
- **UP**: ready **>= desired** again

### Configure (Controller env vars)

Set these under the `controller:` service in `docker-compose.yml`:

- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_SECURE` (`true` for 465, otherwise usually `false`)
- `SMTP_USER` / `SMTP_PASS` (optional, depending on SMTP server)
- `EMAIL_FROM` (default `perfect-system@localhost`)
- `EMAIL_TO` (comma-separated recipients)
- `EMAIL_SUBJECT_PREFIX` (default `[Perfect System] `)
- `PUBLIC_UI_URL` (optional link included in email)

Alert behavior knobs:
- `ALERT_DOWN_CONFIRM_MS` / `ALERT_UP_CONFIRM_MS` (default `0`)
- `ALERT_COOLDOWN_MS` (default `0`)
- `ALERT_STARTUP_GRACE_MS` (default `5000`)

### Duplicate-email fix (included)

This project version prevents duplicates by:
- **Blocking overlapping reconcile ticks** (no concurrent reconcile loops).
- **De-duplicating `EMAIL_TO` recipients** (same address won’t receive twice).

---

## Project structure

```
.
├─ docker-compose.yml
├─ examples/
│  ├─ api-v1.yaml
│  ├─ api-v2.yaml
│  └─ api-canary.yaml
└─ services/
   ├─ api/         # UI + REST endpoints + SSE + Swagger
   ├─ controller/  # reconcile loop + metrics + email alerts
   ├─ agent/       # simulated pods + probe endpoints
   ├─ v1/ v2/ v3/  # (optional) FastAPI demo services (not used by docker-compose)
```

---

## Troubleshooting

### “No email is sent”
- Ensure `SMTP_HOST` is set and `EMAIL_TO` is non-empty.
- Check controller logs for SMTP errors (`Email send failed: ...`).

---

## License / usage

Licensed under the MIT License.
