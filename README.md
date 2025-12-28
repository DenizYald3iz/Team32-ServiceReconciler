# Team32 Service Reconciler — *Perfect System* (Tron UI) + Secure Failover Monitor

A **teaching / demo project** that shows two related ideas:

1) **Desired-state orchestration** (Kubernetes-style reconciliation) — you declare what you want (*replicas, rollout strategy, probes, autoscaling*), and a Controller reconciles until the simulated cluster matches.
2) A **secure monitoring dashboard** (FastAPI) that logs health checks + audit actions, supports “chaos” toggles, and can automatically fail over between **v1 → v2 → v3** demo services.

> This is a **simulation**: no real Kubernetes cluster is required. It’s built to be easy to run locally and easy to explain in a classroom demo.

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick start: Perfect System (Docker)](#quick-start-perfect-system-docker)
- [Using the Perfect System API](#using-the-perfect-system-api)
- [Secure Failover Monitor (FastAPI demo)](#secure-failover-monitor-fastapi-demo)
- [Security notes](#security-notes)
- [Tests (pytest)](#tests-pytest)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

### Perfect System (Node/Express + Docker Compose)
- **Tron UI** dashboard (live updates via Server-Sent Events).
- **Apply a Service spec** in YAML (`POST /apply`) and watch reconciliation.
- **Pods + replicas**: Controller creates/terminates simulated pods to match desired replicas.
- **Readiness & liveness probes** (simulated checks).
- **Autoscaling** based on simulated CPU (`POST /load`).
- **Rollouts**:
  - Blue/Green
  - Canary (step-based)
- **Chaos testing**: kill N pods (`POST /chaos/kill`).
- **Round-robin load balancer**: pick next healthy pod (`GET /lb/select`) and proxy (`/proxy/*`).
- **Prometheus-style metrics** exposed by Controller and proxied by API (`GET /metrics`).
- Optional **email alerts** when a service transitions **DOWN** and later **UP** (Controller env vars).

### Secure Failover Monitor (Python/FastAPI)
- Password-protected **HTML dashboard** (HTTP Basic Auth).
- **Audit logging** (who clicked what) + **health logs** stored in SQLite (`monitor.db` by default).
- **Chaos toggles** that make the demo service slow / corrupted (CPU load + data corruption).
- **Smart failover** logic that switches between **v1/v2/v3** if the active one fails (cooldown + failure threshold).
- Optional email notification via `.env` (Gmail SMTP).

---

## Architecture

### Perfect System (Docker)
```
┌───────────┐     desired state (YAML)      ┌───────────────┐
│  Tron UI  │  ──────────────────────────▶  │      API      │  (Express)
│  (web)    │   SSE: /events, state: /state │  :8080        │
└───────────┘                                └──────┬────────┘
                                                    │
                                                    │ state.json (volume)
                                                    ▼
                                             ┌───────────────┐
                                             │   Controller  │  reconcile loop
                                             │    :8090      │  + /metrics
                                             └──────┬────────┘
                                                    │
                                                    ▼
                                             ┌───────────────┐
                                             │     Agent     │  simulates pods
                                             │     :8070     │
                                             └───────────────┘
```

### Secure Failover Monitor (FastAPI)
- `services/v1`, `services/v2`, `services/v3` are small FastAPI demo apps.
- `main.py` is the monitoring dashboard that checks `/health` of the active version and can switch to the next one.

---

## Quick start: Perfect System (Docker)

### Requirements
- Docker + Docker Compose

### Run
```bash
cd Team32-ServiceReconciler
docker compose up --build
```

Open:
- **Tron UI:** http://localhost:8080  
- **Swagger API docs:** http://localhost:8080/docs  
- **Cluster state (JSON):** http://localhost:8080/state  
- **Prometheus metrics:** http://localhost:8080/metrics  

Stop:
```bash
docker compose down
```

---

## Using the Perfect System API

### Apply a service YAML
The API accepts a single `kind: Service` YAML document.

Example (also available in `examples/`):
```bash
curl -X POST http://localhost:8080/apply   -H "Content-Type: application/yaml"   --data-binary @examples/api-v1.yaml
```

### Chaos: kill pods
```bash
curl -X POST "http://localhost:8080/chaos/kill?service=api&count=2"
```

### Simulated load (autoscaling demo)
```bash
curl -X POST "http://localhost:8080/load?service=api&cpu=80"
```

### Manual scaling (+1 / -1)
```bash
curl -X POST "http://localhost:8080/scale?service=api&delta=1"
curl -X POST "http://localhost:8080/scale?service=api&delta=-1"
```

### Load balancer selection
```bash
curl "http://localhost:8080/lb/select?service=api"
```

---

## Service YAML format

Minimum:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  replicas: 3
  image: local://demo@v1
```

Supported fields (high level):
- `spec.replicas` (int)
- `spec.image` (`local://demo@v1`, `local://demo@v2`, …)
- `spec.env` (list of `{name,value}`)
- `spec.readinessProbe.httpGet.path`
- `spec.livenessProbe.httpGet.path`
- `spec.autoscale` (targetCPU, min/max, etc. — used by the Controller simulation)
- `spec.rollout.strategy`: `BlueGreen` or `Canary`
- `spec.rollout.steps` (for Canary)

See the ready-to-run examples:
- `examples/api-v1.yaml`
- `examples/api-v2.yaml`
- `examples/api-canary.yaml`

---

## Secure Failover Monitor (FastAPI demo)

This is a **separate local demo** (no Docker required) that focuses on monitoring + audit logging + failover.

### Requirements
- Python 3.10+ recommended

### Install
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### Run the three demo services
In three terminals:
```bash
uvicorn services.v1.app:app --port 8001
uvicorn services.v2.app:app --port 8002
uvicorn services.v3.app:app --port 8003
```

### Run the dashboard
```bash
uvicorn main:app --port 8000
```

Open:
- Dashboard: http://localhost:8000  
  - **Username:** `admin`
  - **Password:** `secure123`

> The dashboard writes logs to `monitor.db` by default. Tests override this path to use a temporary DB.

### Optional email notifications
Copy `.env.example` to `.env` and fill the variables:
```bash
cp .env.example .env
# edit .env
```

---

## Security notes

This repo intentionally demonstrates a few **secure-coding building blocks**:
- **Optional API key** protection for Perfect System endpoints (set `X_API_KEY` in `docker-compose.yml` and include `X-API-Key` header).
- **HTTP Basic Auth** for the FastAPI dashboard (constant-time compare via `secrets.compare_digest`).
- **Audit logging** to SQLite for security-relevant actions (chaos, failover, reset, etc.).
- Sensitive values (email credentials) are read from environment variables (`.env`).

Limitations (by design):
- The FastAPI demo uses a **hard-coded** admin user/pass for classroom simplicity — treat it as a demo, not production.
- The Perfect System is a simulation and does not implement full Kubernetes semantics.

---

## Tests (pytest)

### Run
```bash
pytest -q
```

### With coverage
```bash
pytest --cov --cov-report=term-missing
```

### What the tests cover
- `tests/test_main_py.py`
  - Dashboard requires Basic Auth (`/`)
  - Audit logging writes rows to SQLite
  - Health-check helper returns OK vs DOWN behavior (patched requests)
- `tests/test_services.py`
  - v1/v2 CPU simulation + reset endpoints
  - v1/v2 corruption makes root and health fail, then recovery after reset
  - v3 root + health are stable
- `tests/conftest.py`
  - Provides a minimal **docker module stub** so `main.py` can be imported during tests without a Docker daemon.

---

## Project structure

```
Team32-ServiceReconciler/
├─ docker-compose.yml
├─ examples/                 # YAML examples to apply
├─ services/
│  ├─ api/                   # Express API + Tron UI
│  ├─ controller/            # Reconcile loop + metrics + optional email alerts
│  ├─ agent/                 # Simulated cluster runtime (pods)
│  ├─ v1/ v2/ v3/            # FastAPI demo services for the Python dashboard
├─ main.py                   # Secure Failover Monitor dashboard (FastAPI)
├─ tests/                    # pytest suite
├─ requirements.txt
├─ requirements-dev.txt
└─ LICENSE.txt
```

---

## Troubleshooting

### UI loads, but nothing changes
- Ensure all 3 Docker services are up: `docker compose ps`
- Check logs: `docker compose logs -f --tail=200`

### API returns 401 Unauthorized
- You likely enabled `X_API_KEY`. Send a header:
  ```bash
  curl -H "X-API-Key: changeme" ...
  ```

### “No email is sent” (Controller or FastAPI demo)
- Verify SMTP credentials and recipient.
- For Gmail, you typically need an **App Password** (2FA enabled).

### Ports already in use
- Perfect System uses `8080/8090/8070`
- FastAPI demo uses `8000/8001/8002/8003`

---

## License

MIT — see `LICENSE.txt`.
