import express from 'express';
import cors from 'cors';
import yaml from 'js-yaml';
import fetch from 'node-fetch';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import swaggerUi from 'swagger-ui-express';
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
    for (const res of clients) res.write(payload);
  } catch {}
}
app.get('/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
  });
  res.write('retry: 1000\n\n');
  clients.add(res);
  req.on('close', () => clients.delete(res));
});
app.post('/_push', (req, res) => { broadcastState(); res.json({ ok: true }); });

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
    '/load': { post: { summary: 'Set simulated CPU for a service', parameters: [{in:'query',name:'service'},{in:'query',name:'cpu'}], responses: {'200':{}} } }
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
  res.json({ ok: true, replicas: afterCount });
});

const PORT = 8080;
app.listen(PORT, () => console.log(`API listening on :${PORT}`));
