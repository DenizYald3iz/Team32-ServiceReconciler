# Dynamic Service Reconciler (DSR)
Seamless inter-microservice transition system (single-node demo).

## What you get
- **Health monitoring**: polls each instance's health endpoint.
- **Self-healing**: restarts/replace containers after consecutive failed checks.
- **Version rollouts**: canary-style rollout by gradually changing routing weights.
- **Load balancing**: in-process gateway does weighted version selection + round-robin across instances.
- **Status + audit trail**: SQLite DB + `/events` endpoint + simple `/dashboard` page.

## Project structure
```
.
├─ dsr/                # core library modules
├─ main.py             # FastAPI entrypoint
├─ cli.py              # tiny CLI for registering & rolling out
├─ requirements.txt
└─ examples/
   └─ example_service/ # a tiny FastAPI microservice with /health + /version
```

## Quick start (recommended: docker-compose)
Prereqs: Docker + docker-compose.

1) Build demo service images:
```bash
docker build -t dsr-svc:v1 services/v1
docker build -t dsr-svc:v2 services/v2
```

2) Start DSR (runs inside Docker and controls Docker via the mounted socket):
```bash
cp .env.example .env  # optional
mkdir -p data         # persistent SQLite DB (docker-compose bind mount)
docker compose up --build
```

3) Register a service version (from your host machine):
```bash
python cli.py register --service example --version v1 --image dsr-svc:v1 --internal-port 80 --replicas 2 --weight 100
```

4) Call through the gateway:
```bash
curl http://localhost:8000/gateway/example/version
```

5) Canary rollout to v2:
```bash
python cli.py rollout --service example --to-version v2 --image dsr-svc:v2 --internal-port 80 --replicas 2 --canary-weight 10 --step-percent 25 --step-interval-s 10 --auto
```

Open the dashboard:
- http://localhost:8000/dashboard

## Email alerts (optional)
Set these env vars before starting `uvicorn`:
```
DSR_ENABLE_EMAIL=true
DSR_SMTP_HOST=smtp.gmail.com
DSR_SMTP_PORT=587
DSR_SMTP_USER=you@gmail.com
DSR_SMTP_PASSWORD=YOUR_APP_PASSWORD
DSR_EMAIL_FROM=you@gmail.com
DSR_EMAIL_TO=receiver@gmail.com
```

## Notes
- DSR expects health endpoints to return JSON `{ "status": "healthy" }`.
- For security, health checks are **path-based** (e.g. `/health`) and combined with an internally computed container URL.
- This is a teaching/demo project (not a production orchestrator).
