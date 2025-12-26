import express from 'express';
import cors from 'cors';
import yaml from 'js-yaml';
import fetch from 'node-fetch';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import swaggerUi from 'swagger-ui-express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { readStore, writeStore, recordEvent } from './store.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AGENT_URL = process.env.AGENT_URL || 'http://agent:8070';
const CONTROLLER_URL = process.env.CONTROLLER_URL || 'http://controller:8090';
const X_API_KEY = process.env.X_API_KEY || '';

const app = express();
app.use(express.text({ type: ['text/*', 'application/yaml', 'application/x-yaml'] }));
app.use(express.json());
app.use(cors());

function authOk(req) {
  if (!X_API_KEY) return true;
  return req.headers['x-api-key'] === X_API_KEY;
}
function requireAuth(req, res, next) {
  if (!authOk(req)) return res.status(401).json({ error: 'Unauthorized' });
  next();
}

// --- SSE for live state ---
const clients = new Set();
function broadcastState() {
  try {
    const s = readStore();
    const payload = `data: ${JSON.stringify(s)}\n\n`;
    const deadClients = [];
    for (const res of clients) {
      try {
        res.write(payload);
      } catch (err) {
        // Client disconnected, mark for removal
        deadClients.push(res);
      }
    }
    // Remove dead clients
    deadClients.forEach(res => clients.delete(res));
  } catch (err) {
    console.error('[SSE] Error broadcasting state:', err.message);
  }
}
app.get('/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no', // Disable buffering in nginx if present
  });
  res.write('retry: 1000\n\n');
  clients.add(res);
  
  // Send initial state
  try {
    const s = readStore();
    res.write(`data: ${JSON.stringify(s)}\n\n`);
  } catch (err) {
    console.error('[SSE] Error sending initial state:', err.message);
  }
  
  req.on('close', () => {
    clients.delete(res);
  });
  
  req.on('error', () => {
    clients.delete(res);
  });
});
app.post('/_push', (req, res) => { 
  broadcastState(); 
  res.json({ ok: true }); 
});

// --- Round-Robin Load Balancer ---
// Track current index per service for round-robin
const roundRobinIndex = new Map(); // service -> current index

function getHealthyPods(serviceName = null) {
  try {
    const state = readStore();
    let pods = Object.values(state.pods || {});
    
    // Filter healthy pods
    pods = pods.filter(p => {
      if (!p.ready || p.phase !== 'Running') return false;
      if (p.terminating) return false;
      if (serviceName && p.service !== serviceName) return false;
      return true;
    });
    
    // Sort by port for stable ordering
    pods.sort((a, b) => (a.port || 0) - (b.port || 0));
    return pods;
  } catch (err) {
    console.error('[LB] Error reading state:', err.message);
    return [];
  }
}

function selectNextPod(serviceName) {
  const healthyPods = getHealthyPods(serviceName);
  if (healthyPods.length === 0) {
    // Reset index when no healthy pods
    roundRobinIndex.delete(serviceName);
    return null;
  }
  
  const currentIndex = roundRobinIndex.get(serviceName) ?? -1;
  
  // Ensure index is within bounds (in case pod list changed)
  const safeIndex = Math.max(-1, Math.min(currentIndex, healthyPods.length - 1));
  const nextIndex = (safeIndex + 1) % healthyPods.length;
  roundRobinIndex.set(serviceName, nextIndex);
  
  return healthyPods[nextIndex];
}

// Load balancer endpoint - demonstrates round-robin selection
app.get('/lb/select', (req, res) => {
  const serviceName = req.query.service || 'api';
  const pod = selectNextPod(serviceName);
  const allHealthy = getHealthyPods(serviceName);
  
  if (!pod) {
    return res.status(503).json({ 
      error: 'Service Unavailable', 
      message: `No healthy pods available for service: ${serviceName}`,
      healthyPods: []
    });
  }
  
  res.json({
    selected: {
      id: pod.id,
      port: pod.port,
      service: pod.service,
      ready: pod.ready,
      phase: pod.phase
    },
    healthyPods: allHealthy.map(p => ({
      id: p.id,
      port: p.port,
      service: p.service
    })),
    totalHealthy: allHealthy.length
  });
});

// Load balancer proxy middleware for /proxy/* path
app.use('/proxy/*', async (req, res, next) => {
  // Extract service name from query or use default
  const serviceName = req.query.service || 'api';
  
  // Try to find a healthy pod with retry logic
  let attempts = 0;
  const maxAttempts = Math.min(3, getHealthyPods(serviceName).length || 1);
  const triedPods = new Set();
  
  while (attempts < maxAttempts) {
    const pod = selectNextPod(serviceName);
    
    if (!pod) {
      return res.status(503).json({ 
        error: 'Service Unavailable', 
        message: `No healthy pods available for service: ${serviceName}` 
      });
    }
    
    // Skip if we already tried this pod
    if (triedPods.has(pod.id)) {
      attempts++;
      continue;
    }
    triedPods.add(pod.id);
    
    // In a real system, pods would have HTTP servers on their ports
    // For this demo, we'll try to proxy to the pod port
    // Note: In production, pods would be accessible via their ports or through a service mesh
    const targetUrl = `http://localhost:${pod.port}`;
    const targetPath = req.path.replace('/proxy', '') || '/';
    
    try {
      // Forward the request to the selected pod
      const fetchOptions = {
        method: req.method,
        headers: { ...req.headers },
      };
      
      // Remove problematic headers
      delete fetchOptions.headers.host;
      delete fetchOptions.headers['content-length'];
      
      // Add body for non-GET requests
      if (req.method !== 'GET' && req.method !== 'HEAD' && req.body) {
        if (typeof req.body === 'string') {
          fetchOptions.body = req.body;
        } else {
          fetchOptions.body = JSON.stringify(req.body);
          fetchOptions.headers['content-type'] = 'application/json';
        }
      }
      
      const response = await fetch(targetUrl + targetPath, fetchOptions);
      
      // Forward response headers
      response.headers.forEach((value, key) => {
        const lowerKey = key.toLowerCase();
        if (lowerKey !== 'content-encoding' && lowerKey !== 'transfer-encoding' && lowerKey !== 'connection') {
          res.setHeader(key, value);
        }
      });
      
      // Forward status
      res.status(response.status);
      
      // Stream response body
      const body = await response.text();
      res.send(body);
      return; // Success, exit
      
    } catch (err) {
      console.error(`[LB] Error proxying to pod ${pod.id} (port ${pod.port}):`, err.message);
      attempts++;
      
      // If this was the last attempt, don't try another pod
      if (attempts >= maxAttempts) {
        break;
      }
      
      // Refresh healthy pods list in case it changed
      const refreshedHealthy = getHealthyPods(serviceName);
      if (refreshedHealthy.length === 0) {
        break; // No more healthy pods
      }
      
      // Continue to next pod (round-robin will select next automatically)
    }
  }
  
  // All attempts failed
  res.status(503).json({ 
    error: 'Service Unavailable', 
    message: `All healthy pods failed for service: ${serviceName}`,
    triedPods: Array.from(triedPods)
  });
});

// Generic load balancer for all non-API routes (optional - can be enabled)
// This would route all requests except /state, /apply, /chaos, etc. to pods
// For now, we'll keep it disabled and use /proxy/* explicitly

// Static UI
app.use(express.static(path.join(__dirname, 'public')));
app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));

// OpenAPI (minimal)
const swagger = {
  openapi: '3.0.0',
  info: { title: 'Perfect System API', version: '1.0.0' },
  paths: {
    '/apply': { post: { summary: 'Apply a Service spec (YAML)', responses: { '200': { description: 'OK' } } } },
    '/state': { get: { summary: 'Get cluster state', responses: { '200': { } } } },
    '/chaos/kill': { post: { summary: 'Kill N pods for a service', parameters: [{in:'query',name:'service'},{in:'query',name:'count'}], responses: {'200':{}} } },
    '/load': { post: { summary: 'Set simulated CPU for a service', parameters: [{in:'query',name:'service'},{in:'query',name:'cpu'}], responses: {'200':{}} } },
    '/lb/select': { get: { summary: 'Round-robin load balancer: select next healthy pod', parameters: [{in:'query',name:'service'}], responses: {'200':{description:'Selected pod info'},'503':{description:'No healthy pods'}} } },
    '/proxy/*': { get: { summary: 'Proxy request to healthy pods using round-robin', parameters: [{in:'query',name:'service'}], responses: {'200':{description:'Proxied response'},'503':{description:'Service unavailable'}} } },
    '/events': { get: { summary: 'SSE stream for real-time state updates', responses: {'200':{description:'Event stream'}} } }
  }
};
app.use('/docs', swaggerUi.serve, swaggerUi.setup(swagger));

// State
app.get('/state', (req,res)=> res.json(readStore()));

// Proxy metrics from controller
app.get('/metrics', async (req, res) => {
  try {
    const resp = await fetch(`${CONTROLLER_URL}/metrics`);
    if (!resp.ok) {
      return res.status(resp.status).send(`Controller /metrics error: ${resp.statusText}`);
    }
    const text = await resp.text();
    res.setHeader('Content-Type', 'text/plain');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.send(text);
  } catch (e) {
    res.status(500).send(`Metrics fetch error: ${e.message}`);
  }
});

// Apply YAML spec (single Service)
app.post('/apply', requireAuth, (req, res) => {
  const text = typeof req.body === 'string' ? req.body : (req.body.yaml || '');
  let doc;
  try { doc = yaml.load(text); }
  catch (e) { return res.status(400).json({ error: 'Invalid YAML', detail: e.message }); }
  if (!doc || doc.kind !== 'Service') return res.status(400).json({ error: 'Expected kind: Service' });
  const name = doc.metadata?.name;
  const replicas = doc.spec?.replicas ?? 1;
  const img = String(doc.spec?.image || 'local://demo@v1');
  const digest = img.includes('@') ? img.split('@')[1] : img;
  if (!name) return res.status(400).json({ error: 'metadata.name required' });
  const state = readStore();
  const rollout = doc.spec?.rollout || { strategy: 'BlueGreen' };
  const readinessProbe = doc.spec?.readinessProbe || null;
  const livenessProbe = doc.spec?.livenessProbe || null;
  const autoscale = doc.spec?.autoscale || null;
  const env = doc.spec?.env || [];
  state.services[name] = {
    name, replicas, digest, env, rollout,
    readinessProbe, livenessProbe, autoscale,
    cpu: 0, // simulated cpu avg
  };
  recordEvent(state, 'INFO', name, null, `Applied Desired replicas=${replicas}, digest=${digest}`, 'Desired state updated — Controller will reconcile.');
  writeStore(state);
  broadcastState(); // Immediate SSE update
  res.json({ ok: true, service: state.services[name] });
});

// Chaos: kill N pods for a service
app.post('/chaos/kill', requireAuth, async (req, res) => {
  const svc = req.query.service;
  const count = parseInt(req.query.count || '1', 10);
  const state = readStore();
  const pods = Object.values(state.pods).filter(p => p.service === svc && p.phase === 'Running');
  const toKill = pods.slice(0, count);
  for (const p of toKill) {
    await fetch(`${AGENT_URL}/kill`, { method: 'POST', headers: {'Content-Type':'application/json', ...(X_API_KEY?{'X-API-Key':X_API_KEY}:{})}, body: JSON.stringify({ podId: p.id }) });
    recordEvent(state, 'WARN', svc, p.id, 'Chaos kill', 'Intentional failure to showcase self-healing.');
    delete state.pods[p.id];
  }
  writeStore(state);
  broadcastState(); // Immediate SSE update
  res.json({ killed: toKill.map(p=>p.id) });
});

// Simulated load for autoscaling
app.post('/load', requireAuth, (req,res)=>{
  const svc = req.query.service;
  const cpu = Math.max(0, Math.min(100, parseInt(req.query.cpu||'0',10)));
  const st = readStore();
  if (!st.services[svc]) return res.status(404).json({error:'service not found'});
  st.services[svc].cpu = cpu;
  recordEvent(st, 'INFO', svc, null, `Load set to ${cpu}%`,'Autoscaler will react if above/below target.');
  writeStore(st);
  broadcastState(); // Immediate SSE update
  res.json({ ok:true, cpu });
});

// Tiny push to clients after writes (best-effort)
setInterval(() => fetch(`http://localhost:8080/_push`, { method:'POST' }).catch(()=>{}), 1500);


// Manual scale: /scale?service=api&delta=1 (or -1)
app.post('/scale', requireAuth, (req, res) => {
  const svcName = String(req.query.service || '');
  const delta = parseInt(req.query.delta || '0', 10);
  const state = readStore();
  const svc = state.services[svcName];
  if (!svc) return res.status(404).json({ error: 'service not found' });
  const before = svc.replicas || 0;
  const afterCount = Math.max(0, before + delta);
  svc.replicas = afterCount;
  recordEvent(state, 'INFO', svcName, null, `Manual scale ${delta>0?'+1':'-1'} → ${afterCount}`, 'User-requested change to Desired replicas.');
  writeStore(state);
  broadcastState(); // Immediate SSE update
  res.json({ ok: true, replicas: afterCount });
});

const PORT = 8080;
app.listen(PORT, () => console.log(`API listening on :${PORT}`));
