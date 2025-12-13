from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse

from dsr import db
from dsr.api_models import RegisterVersionRequest, RolloutRequest, ScaleRequest, WeightRequest
from dsr.docker_ops import validate_health_path, validate_service_name, validate_version
from dsr.gateway import NoHealthyBackends, select_backend
from dsr.reconciler import Reconciler
from dsr.rollouts import RolloutManager
from dsr.runtime import RuntimeState
from dsr.settings import settings


app = FastAPI(title="Dynamic Service Reconciler", version="1.0")

runtime = RuntimeState()
reconciler = Reconciler(runtime=runtime, fail_threshold=2)
rollouts = RolloutManager(runtime=runtime)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    reconciler.start()
    db.log_event("INFO", "API started")


@app.get("/")
def home() -> dict[str, Any]:
    return {
        "status": "ok",
        "poll_interval_s": settings.poll_interval_s,
        "docker_network": settings.docker_network,
        "endpoints": {
            "services": "/services",
            "events": "/events",
            "dashboard": "/dashboard",
            "gateway": "/gateway/{service}/{path}",
            "metrics": "/metrics",
        },
    }


@app.get("/services")
def list_services() -> dict[str, Any]:
    services = db.list_services()
    versions = db.list_versions()
    by_service: dict[str, list[dict[str, Any]]] = {}
    svc_id_to_name = {s.id: s.name for s in services}
    for v in versions:
        by_service.setdefault(svc_id_to_name.get(v.service_id, str(v.service_id)), []).append(
            {
                "version": v.version,
                "image": v.image,
                "internal_port": v.internal_port,
                "health_path": v.health_path,
                "replicas": v.desired_replicas,
                "weight": v.route_weight,
                "state": v.state,
            }
        )
    return {"services": [{"name": s.name, "versions": by_service.get(s.name, [])} for s in services]}


@app.post("/services")
def register_version(req: RegisterVersionRequest) -> dict[str, Any]:
    try:
        validate_service_name(req.service)
        validate_version(req.version)
        validate_health_path(req.health_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    v = db.upsert_version(
        service_name=req.service,
        version=req.version,
        image=req.image,
        internal_port=req.internal_port,
        health_path=req.health_path,
        desired_replicas=req.replicas,
        route_weight=req.weight,
        state=req.state,
    )
    db.log_event("INFO", f"Registered/updated version {req.version}", service_name=req.service, version=req.version)
    return {"ok": True, "version_id": v.id}


@app.post("/services/{service}/versions/{version}/scale")
def scale_version(service: str, version: str, req: ScaleRequest) -> dict[str, Any]:
    v = db.get_version(service, version)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    db.set_version_replicas(v.id, int(req.replicas))
    db.log_event("INFO", f"Set replicas={req.replicas}", service_name=service, version=version)
    return {"ok": True}


@app.post("/services/{service}/versions/{version}/weight")
def set_weight(service: str, version: str, req: WeightRequest) -> dict[str, Any]:
    v = db.get_version(service, version)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    db.set_version_weight(v.id, int(req.weight))
    db.log_event("INFO", f"Set weight={req.weight}", service_name=service, version=version)
    return {"ok": True}


@app.post("/services/{service}/versions/{version}/retire")
def retire_version(service: str, version: str) -> dict[str, Any]:
    v = db.get_version(service, version)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    db.set_version_state(v.id, "retired")
    db.set_version_weight(v.id, 0)
    db.set_version_replicas(v.id, 0)
    db.log_event("INFO", "Retired version", service_name=service, version=version)
    return {"ok": True}


@app.get("/services/{service}/versions/{version}/instances")
def version_instances(service: str, version: str) -> dict[str, Any]:
    v = db.get_version(service, version)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    inst = []
    for i in db.list_instances(v.id):
        inst.append(
            {
                "container_id": i.container_id,
                "container_name": i.container_name,
                "status": i.status,
                "last_health_ts": i.last_health_ts,
                "last_latency_ms": i.last_latency_ms,
                "restart_count": i.restart_count,
            }
        )
    return {"service": service, "version": version, "instances": inst}


@app.post("/services/{service}/rollout")
def start_rollout(service: str, req: RolloutRequest, background: BackgroundTasks) -> dict[str, Any]:
    try:
        validate_service_name(service)
        validate_version(req.to_version)
        validate_health_path(req.health_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rollout_id = rollouts.start_rollout(
        service=service,
        new_version=req.to_version,
        image=req.image,
        internal_port=req.internal_port,
        health_path=req.health_path,
        replicas=req.replicas,
        canary_weight=req.canary_weight,
        step_percent=req.step_percent,
        step_interval_s=req.step_interval_s,
        auto=req.auto,
        max_wait_s=req.max_wait_s,
    )
    return {"ok": True, "rollout_id": rollout_id, "auto": req.auto}


@app.post("/rollouts/{rollout_id}/continue")
def continue_rollout(rollout_id: str) -> dict[str, Any]:
    try:
        st = rollouts.continue_rollout(rollout_id)
        return {"ok": True, "rollout": st.__dict__}
    except KeyError:
        raise HTTPException(status_code=404, detail="rollout not found")


@app.get("/rollouts")
def list_rollouts() -> dict[str, Any]:
    return {"rollouts": [r.__dict__ for r in runtime.list_rollouts()]}


@app.get("/events")
def events(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(1000, int(limit)))
    return {"events": db.latest_events(limit=limit)}


@app.get("/metrics")
def metrics() -> Response:
    # Minimal Prometheus-style counters (text format)
    services = db.list_services()
    versions = db.list_versions()
    lines = ["# HELP dsr_services Number of known services", "# TYPE dsr_services gauge"]
    lines.append(f"dsr_services {len(services)}")
    lines.append("# HELP dsr_versions Number of known versions")
    lines.append("# TYPE dsr_versions gauge")
    lines.append(f"dsr_versions {len(versions)}")

    # Instance health
    up = 0
    down = 0
    for v in versions:
        for i in db.list_instances(v.id):
            if i.status == "up":
                up += 1
            else:
                down += 1
    lines.append("# HELP dsr_instances_up Healthy instances")
    lines.append("# TYPE dsr_instances_up gauge")
    lines.append(f"dsr_instances_up {up}")
    lines.append("# HELP dsr_instances_down Unhealthy/starting instances")
    lines.append("# TYPE dsr_instances_down gauge")
    lines.append(f"dsr_instances_down {down}")
    return PlainTextResponse("\n".join(lines) + "\n")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    # No templates needed; keep it single-file.
    return """
<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>Dynamic Service Reconciler</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 20px; }
      .row { display:flex; gap: 16px; flex-wrap: wrap; }
      .card { border: 1px solid #ddd; border-radius: 12px; padding: 14px; min-width: 280px; }
      code { background:#f5f5f5; padding:2px 6px; border-radius: 6px; }
      .muted { color: #666; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border-bottom: 1px solid #eee; text-align: left; padding: 8px; }
    </style>
  </head>
  <body>
    <h2>Dynamic Service Reconciler</h2>
    <p class='muted'>Refreshes every 3s. API: <code>/services</code>, events: <code>/events</code>, gateway: <code>/gateway/&lt;service&gt;/...</code></p>
    <div class='row'>
      <div class='card' style='flex:1'>
        <h3>Services</h3>
        <div id='services'></div>
      </div>
      <div class='card' style='flex:1'>
        <h3>Events</h3>
        <div id='events'></div>
      </div>
    </div>
    <script>
      async function refresh() {
        const svc = await fetch('/services').then(r => r.json());
        const ev = await fetch('/events?limit=20').then(r => r.json());

        const s = document.getElementById('services');
        s.innerHTML = '';
        (svc.services || []).forEach(ss => {
          const div = document.createElement('div');
          div.innerHTML = `<h4>${ss.name}</h4>`;
          const table = document.createElement('table');
          table.innerHTML = `<tr><th>version</th><th>state</th><th>replicas</th><th>weight</th><th>image</th></tr>`;
          (ss.versions || []).forEach(v => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${v.version}</td><td>${v.state}</td><td>${v.replicas}</td><td>${v.weight}%</td><td><code>${v.image}</code></td>`;
            table.appendChild(tr);
          });
          div.appendChild(table);
          s.appendChild(div);
        });

        const e = document.getElementById('events');
        e.innerHTML = '';
        const ul = document.createElement('ul');
        (ev.events || []).forEach(x => {
          const li = document.createElement('li');
          li.textContent = `[${x.ts}] ${x.level} ${x.service_name || ''} ${x.version || ''} - ${x.message}`;
          ul.appendChild(li);
        });
        e.appendChild(ul);
      }
      refresh();
      setInterval(refresh, 3000);
    </script>
  </body>
</html>
"""


@app.api_route("/gateway/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def gateway(service: str, path: str, request: Request) -> Response:
    try:
        target, chosen_version = select_backend(service, runtime)
    except NoHealthyBackends as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Forward request
    upstream_url = f"{target.base_url}/{path.lstrip('/')}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    hop_by_hop = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop and k.lower() != "host"}
    body = await request.body()

    async with httpx.AsyncClient(timeout=settings.gateway_timeout_s, follow_redirects=False) as client:
        try:
            resp = await client.request(request.method, upstream_url, headers=headers, content=body)
        except httpx.RequestError as e:
            db.log_event(
                "ERROR",
                f"Gateway error talking to {service} {chosen_version}: {type(e).__name__}: {e}",
                service_name=service,
                version=chosen_version,
            )
            raise HTTPException(status_code=502, detail="upstream error")

    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in hop_by_hop}
    out_headers["X-DSR-Service"] = service
    out_headers["X-DSR-Version"] = chosen_version
    return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)
