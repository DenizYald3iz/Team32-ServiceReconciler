import fetch from 'node-fetch';
import http from 'http';
import { readStore, writeStore, recordEvent, now } from './store.js';
import { mailEnabled, sendServiceAlert } from './mailer.js';

const API_URL = process.env.API_URL || 'http://api:8080';
const AGENT_URL = process.env.AGENT_URL || 'http://agent:8070';
const TICK_MS = parseInt(process.env.TICK_MS||'1000',10);
const X_API_KEY = process.env.X_API_KEY || '';

function headers() { return { 'Content-Type':'application/json', ...(X_API_KEY?{'X-API-Key':X_API_KEY}:{}) }; }

function readyCount(state, svc) { return Object.values(state.pods).filter(p=>p.service===svc.name && p.ready).length; }
function podsFor(state, svc) { return Object.values(state.pods).filter(p=>p.service===svc.name); }

async function agentProbe(pod) {
  try { const r = await fetch(`${AGENT_URL}/probe?port=${pod.port}`); return r.status===200; }
  catch { return false; }
}
async function agentSpawn(svc) {
  const resp = await fetch(`${AGENT_URL}/spawn`, { method:'POST', headers: headers(), body: JSON.stringify({ service: svc.name, digest: svc.digest, env: svc.env||[] }) });
  if (!resp.ok) throw new Error('spawn failed'); return await resp.json();
}
async function agentKill(podId) {
  try{ await fetch(`${AGENT_URL}/kill`, { method:'POST', headers: headers(), body: JSON.stringify({ podId }) }); }catch{}
}

function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }

function backoffDelay(p){ const attempt = Math.min(6, (p.backoffAttempt||0)); return Math.pow(2,attempt)*500; } // 0.5s,1s,2s,...

function intEnv(name, def){
  const n = parseInt(String(process.env[name] ?? ''), 10);
  return Number.isFinite(n) ? n : def;
}

const ALERT_DOWN_CONFIRM_MS = intEnv('ALERT_DOWN_CONFIRM_MS', 0);
const ALERT_UP_CONFIRM_MS = intEnv('ALERT_UP_CONFIRM_MS', 0);
const ALERT_COOLDOWN_MS = intEnv('ALERT_COOLDOWN_MS', 0);
const ALERT_STARTUP_GRACE_MS = intEnv('ALERT_STARTUP_GRACE_MS', 5000);

function serviceStatus(desired, ready){
  // "UP" should mean Desired is fully satisfied.
  // Otherwise we consider the service "DOWN" (degraded counts as down) so
  // partial replica loss triggers alerts when Desired > 1.
  if ((desired ?? 0) <= 0) return 'SCALED';
  return (ready ?? 0) >= (desired ?? 0) ? 'UP' : 'DOWN';
}

function startupGraceFor(svc){
  // Prefer explicit env; otherwise: readiness initialDelay + a small buffer.
  if (process.env.ALERT_STARTUP_GRACE_MS !== undefined) return ALERT_STARTUP_GRACE_MS;
  const base = (svc.readinessProbe?.initialDelaySeconds ?? 1) * 1000;
  return Math.max(1000, base + 1000);
}

async function handleServiceAlerts(state, svc){
  state.alerts = state.alerts || {};
  const desired = svc.replicas ?? 0;
  const ready = readyCount(state, svc);
  const digest = svc.digest;
  const statusNow = serviceStatus(desired, ready);
  const ts = now();

  const prev = state.alerts[svc.name];
  if (!prev) {
    // Baseline without sending: we only alert on subsequent transitions.
    state.alerts[svc.name] = {
      status: statusNow,
      lastChangeTs: ts,
      lastNotifiedTs: 0,
      // Treat the current state as the baseline "already known" status.
      // This prevents spurious "UP" alerts after scale-up suppressions.
      notifiedStatus: statusNow,
      pending: null,
      lastDownTs: statusNow === 'DOWN' ? ts : null,
      prevDesired: desired,
      suppressUntil: desired > 0 ? ts + startupGraceFor(svc) : null,
      suppressHandled: false,
    };
    return;
  }

  // If Desired increased (including 0 -> >0), suppress alerts during startup grace.
  // This avoids false "DOWN"/"UP" emails while new replicas are coming online.
  if ((prev.prevDesired ?? 0) < desired) {
    prev.suppressUntil = ts + startupGraceFor(svc);
    prev.suppressHandled = false;
  }

  // Clear suppression when scaling to 0.
  if (desired <= 0) {
    prev.status = 'SCALED';
    prev.pending = null;
    prev.lastChangeTs = ts;
    prev.prevDesired = desired;
    prev.suppressUntil = null;
    prev.suppressHandled = true;
    state.alerts[svc.name] = prev;
    return;
  }

  const confirmMs = statusNow === 'DOWN' ? ALERT_DOWN_CONFIRM_MS : (statusNow === 'UP' ? ALERT_UP_CONFIRM_MS : 0);

  // Pending transition (debounce / confirmation window)
  if (prev.status !== statusNow) {
    if (!prev.pending || prev.pending.to !== statusNow) prev.pending = { to: statusNow, since: ts };
    if (ts - prev.pending.since >= confirmMs) {
      const fromStatus = prev.status;
      prev.status = statusNow;
      prev.lastChangeTs = ts;
      prev.pending = null;
      if (statusNow === 'DOWN') prev.lastDownTs = ts;

      let downtimeMs = null;
      if (statusNow === 'UP' && fromStatus === 'DOWN' && Number.isFinite(prev.lastDownTs)) {
        downtimeMs = ts - prev.lastDownTs;
      }

      await maybeNotify(state, svc.name, statusNow, { desired, ready, digest, ts, downtimeMs, suppress: prev.suppressUntil && ts < prev.suppressUntil });
    }
  } else {
    prev.pending = null;
  }

  // If suppression window ended and we are still DOWN, send a single DOWN alert.
  if (prev.suppressUntil && ts >= prev.suppressUntil && !prev.suppressHandled) {
    prev.suppressHandled = true;
    if (prev.status === 'DOWN') {
      await maybeNotify(state, svc.name, 'DOWN', { desired, ready, digest, ts, downtimeMs: null, suppress: false, force: true });
    }
  }

  prev.prevDesired = desired;
  state.alerts[svc.name] = prev;
}

async function maybeNotify(state, svcName, status, { desired, ready, digest, ts, downtimeMs, suppress, force } = {}) {
  if (suppress) return;
  const rec = state.alerts?.[svcName];
  if (!rec) return;

  // Only alert on UP/DOWN.
  if (status !== 'UP' && status !== 'DOWN') return;

  // Cooldown to avoid rapid flapping spam.
  if (!force && ALERT_COOLDOWN_MS > 0 && rec.lastNotifiedTs && (ts - rec.lastNotifiedTs) < ALERT_COOLDOWN_MS) return;

  // Avoid duplicate same-status notifications.
  if (!force && rec.notifiedStatus === status) return;

  const enabled = mailEnabled();
  const verb = status === 'DOWN' ? 'down' : 'up';
  const level = status === 'DOWN' ? 'WARN' : 'INFO';
  const explain = enabled
    ? `Email sent (service ${verb}).`
    : 'Email not configured; set SMTP_HOST and EMAIL_TO to enable.';
  recordEvent(state, level, svcName, null, `Service ${status}`, explain);

  if (enabled) {
    try {
      await sendServiceAlert({ service: svcName, status, desired, ready, digest, whenTs: ts, downtimeMs });
    } catch (e) {
      recordEvent(state, 'WARN', svcName, null, `Email send failed: ${e.message}`, 'Alerting attempted but SMTP failed.');
    }
  }

  rec.lastNotifiedTs = ts;
  rec.notifiedStatus = status;
}

async function reconcileOnce(){
  const state = readStore();
  state.metrics.readyBySvc = state.metrics.readyBySvc || {};
  state.metrics.restarts = state.metrics.restarts || {};
  const services = Object.values(state.services);

  for (const svc of services) {
    // Drift: kill wrong digest
    for (const p of Object.values(state.pods)) {
      if (p.service!==svc.name) continue;
      if (p.image_digest!==svc.digest && p.phase==='Running') {
        await agentKill(p.id);
        recordEvent(state, 'INFO', svc.name, p.id, 'Kill drift pod (digest mismatch)', 'Blue/Green or Canary: old version draining out.');
        delete state.pods[p.id];
      }
    }

    // Health probes (liveness + readiness)
    for (const p of Object.values(state.pods)) {
      if (p.service!==svc.name) continue;
      const ok = await agentProbe(p);
      p._lastProbe = now();
      
      // Check if pod is still within initialDelaySeconds grace period
      const livenessInitialDelay = (svc.livenessProbe?.initialDelaySeconds ?? 1) * 1000;
      const isWithinInitialDelay = (now() - p.start_ts) < livenessInitialDelay;
      
      if (!ok) {
        // Don't count failures during initialDelaySeconds as restart-worthy
        if (!isWithinInitialDelay) {
          p._fail = (p._fail||0)+1;
          // Liveness
          const lthr = svc.livenessProbe?.failureThreshold ?? 3;
          if (p._fail>=lthr) {
            p.restarts = (p.restarts||0)+1;
            state.metrics.restarts[svc.name] = (state.metrics.restarts[svc.name]||0)+1;
            const delay = backoffDelay(p);
            p.backoffUntil = now()+delay;
            p.backoffAttempt = (p.backoffAttempt||0)+1;
            recordEvent(state, 'WARN', svc.name, p.id, 'Liveness failed — restarting', `Backoff ${delay}ms before respawn.`);
            await agentKill(p.id);
            delete state.pods[p.id];
            continue;
          }
        }
        // Readiness
        p.ready = false;
      } else {
        p._fail = 0;
        // Readiness initialDelaySeconds respected by agent; we still set ready=true on success
        p.ready = true;
      }
    }

    // Backoff timers: skip immediate respawn if backing off
    const active = podsFor(state, svc);
    const targetReplicas = svc.replicas;

    // Rollout strategies
    const strategy = (svc.rollout?.strategy||'BlueGreen');
    if (strategy==='Canary' && (svc.rollout?.steps||[]).length>0) {
      // Determine desired new pods count based on steps and total replicas
      svc._canary = svc._canary || { stepIndex: 0, lastStepTs: 0 };
      const step = svc.rollout.steps[svc._canary.stepIndex] || { percent: 100 };
      const pauseSec = svc.rollout.pauseSeconds || 5;
      const desiredNew = Math.ceil((step.percent/100)*targetReplicas);
      // Count new vs old
      const newPods = active.filter(p=>p.image_digest===svc.digest).length;
      if (newPods < desiredNew) {
        // spawn up to gap
        const gap = desiredNew - newPods;
        for (let i=0;i<gap;i++) {
          const info = await agentSpawn(svc);
          state.pods[info.id] = { id: info.id, pid: info.pid, port: info.port, service: svc.name, image_digest: svc.digest, start_ts: now(), ready: false, phase: 'Running', restarts: 0 };
          recordEvent(state, 'INFO', svc.name, info.id, `Canary spawn (${step.percent}%)`, 'Rolling out gradually: send a slice of traffic to new pods.');
        }
      } else {
        // step advance
        if (now() - (svc._canary.lastStepTs||0) > pauseSec*1000) {
          if (svc._canary.stepIndex < svc.rollout.steps.length-1) {
            svc._canary.stepIndex++;
            svc._canary.lastStepTs = now();
            recordEvent(state, 'INFO', svc.name, null, 'Canary advanced step', `Now at ${svc.rollout.steps[svc._canary.stepIndex].percent}%`);
          } else {
            // Done: scale down old pods
            const oldPods = active.filter(p=>p.image_digest!==svc.digest && p.phase==='Running');
            for (const p of oldPods){ await agentKill(p.id); delete state.pods[p.id]; recordEvent(state,'INFO',svc.name,p.id,'Canary complete — scale down old','New version now at 100%.'); }
          }
        }
      }
      // Enforce total replica cap during canary (manual -1 etc.)
      {
        const activeNow = podsFor(state, svc);
        const haveNow = activeNow.length;
        if (haveNow > targetReplicas) {
          const extra = haveNow - targetReplicas;
          // Prefer killing old-version pods first, then oldest overall
          const olds = activeNow.filter(p=>p.image_digest!==svc.digest);
          const news = activeNow.filter(p=>p.image_digest===svc.digest);
          const victims = (olds.concat(news)).sort((a,b)=>a.start_ts-b.start_ts).slice(0, extra);
          for (const p of victims) {
            await agentKill(p.id);
            delete state.pods[p.id];
            recordEvent(state,'INFO',svc.name,p.id,'ScaleDown kill','Desired < Actual during canary.');
          }
        }
      }

    } else {
      // Blue/Green: ensure all pods match digest; spawn/kill to reach replicas
      const ready = readyCount(state, svc);
      const have = active.length;
      if (have < targetReplicas) {
        const gap = targetReplicas - have;
        for (let i=0;i<gap;i++) {
          const info = await agentSpawn(svc);
          state.pods[info.id] = { id: info.id, pid: info.pid, port: info.port, service: svc.name, image_digest: svc.digest, start_ts: now(), ready: false, phase: 'Running', restarts: 0 };
          recordEvent(state, 'INFO', svc.name, info.id, 'Spawn pod', 'Desired > Actual: creating a new pod to converge.');
        }
      } else if (have > targetReplicas) {
        const extra = have - targetReplicas;
        const candidates = active.sort((a,b)=>a.start_ts-b.start_ts).slice(0,extra);
        for (const p of candidates){ await agentKill(p.id); delete state.pods[p.id]; recordEvent(state,'INFO',svc.name,p.id,'ScaleDown kill','Desired < Actual: removing an extra pod.'); }
      }
    }

    // Autoscaling (simple)
    if (svc.autoscale) {
      const targetCPU = svc.autoscale.targetCPU || 60;
      const min = svc.autoscale.min ?? 1;
      const max = svc.autoscale.max ?? 10;
      const cur = svc.replicas;
      const cpu = svc.cpu || 0;
      if (cpu > targetCPU && cur < max) { svc.replicas = cur+1; recordEvent(state,'INFO',svc.name,null,'HPA scale up','CPU above target.'); }
      if (cpu < targetCPU*0.5 && cur > min) { svc.replicas = cur-1; recordEvent(state,'INFO',svc.name,null,'HPA scale down','CPU well below target.'); }
    }

    // Metrics + alerting (DOWN/UP transitions)
    const readyNow = readyCount(state, svc);
    state.metrics.readyBySvc[svc.name] = readyNow;
    await handleServiceAlerts(state, svc);
  }

  writeStore(state);
  // push state to UI best-effort
  try { await fetch(`${API_URL}/_push`, { method:'POST' }); } catch {}
}

// IMPORTANT: Avoid overlapping reconcile loops.
// reconcileOnce() performs multiple async network calls and can take longer
// than TICK_MS. If we schedule it with setInterval without a lock, multiple
// reconciles can run concurrently and both observe the same transition,
// causing duplicate side-effects (like sending the same alert email twice).
let reconcileInFlight = false;

async function tick() {
  if (reconcileInFlight) return;
  reconcileInFlight = true;
  try {
    await reconcileOnce();
  } catch (err) {
    console.error('reconcile error', err);
  } finally {
    reconcileInFlight = false;
  }
}

// Run immediately, then periodically.
tick();
setInterval(tick, TICK_MS);

// metrics endpoint
const server = http.createServer((req, res)=>{
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }
  
  if (req.url==='/metrics') {
    try {
      const state = readStore();
      let metrics = '';
      
      // Header comments (Prometheus format)
      metrics += '# HELP controller_up Controller is running\n';
      metrics += '# TYPE controller_up gauge\n';
      metrics += 'controller_up 1\n\n';
      
      // Per-service metrics
      metrics += '# HELP api_pods_ready Ready pods per service\n';
      metrics += '# TYPE api_pods_ready gauge\n';
      
      metrics += '# HELP api_pods_desired Desired replicas per service\n';
      metrics += '# TYPE api_pods_desired gauge\n';
      
      metrics += '# HELP api_pods_total Total running pods per service\n';
      metrics += '# TYPE api_pods_total gauge\n';
      
      metrics += '# HELP api_restarts_total Total pod restarts per service\n';
      metrics += '# TYPE api_restarts_total counter\n';
      
      metrics += '# HELP api_events_total Events by service and level\n';
      metrics += '# TYPE api_events_total counter\n';
      
      // Generate actual metric lines
      for (const svc of Object.values(state.services)) {
        const ready = readyCount(state, svc);
        const total = podsFor(state, svc).length;
        const restarts = state.metrics.restarts[svc.name] || 0;
        
        metrics += `api_pods_ready{service="${svc.name}"} ${ready}\n`;
        metrics += `api_pods_desired{service="${svc.name}"} ${svc.replicas}\n`;
        metrics += `api_pods_total{service="${svc.name}"} ${total}\n`;
        metrics += `api_restarts_total{service="${svc.name}"} ${restarts}\n`;
      }
      
      // Event counts by service and level
      metrics += '\n';
      const eventCounts = {};
      for (const event of state.events) {
        const svc = event.svc || 'unknown';
        const level = event.level || 'INFO';
        const key = `${svc}:${level}`;
        eventCounts[key] = (eventCounts[key] || 0) + 1;
      }
      
      for (const [key, count] of Object.entries(eventCounts)) {
        const [svc, level] = key.split(':');
        metrics += `api_events_total{service="${svc}",level="${level}"} ${count}\n`;
      }
      
      res.writeHead(200, {'Content-Type':'text/plain'});
      res.end(metrics);
    } catch (e) {
      res.writeHead(500, {'Content-Type':'text/plain'});
      res.end(`Error: ${e.message}\n`);
    }
  }
  else { res.writeHead(404); res.end(); }
});
server.listen(8090, ()=> console.log('Controller listening on :8090'));
