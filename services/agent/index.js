import express from 'express';

const app = express();
app.use(express.json());

const X_API_KEY = process.env.X_API_KEY || '';
function authOk(req){ if (!X_API_KEY) return true; return req.headers['x-api-key']===X_API_KEY; }
function requireAuth(req,res,next){ if (!authOk(req)) return res.status(401).json({error:'Unauthorized'}); next(); }

// Simulated "pods" registry — not real processes; just ports+env+timers
const pods = new Map(); // port -> { id, service, digest, env, healthy, startTs, readyAfter, liveAfter }
let nextPort = 10000;

function envVal(env, key, def='') {
  const item = (env||[]).find(e=>e.name===key);
  return item ? item.value : def;
}

app.post('/spawn', requireAuth, (req, res)=>{
  const { service, digest, env } = req.body;
  const port = nextPort++;
  const id = `pod-${Math.random().toString(36).slice(2,10)}`;
  const healthy = envVal(env,'HEALTHY','1')==='1';
  const rp = { httpGet: { path: '/healthz' }, initialDelaySeconds: 1, periodSeconds: 2, failureThreshold: 3 };
  const lp = { httpGet: { path: '/livez' }, initialDelaySeconds: 1, periodSeconds: 2, failureThreshold: 3 };
  const readyAfter = Date.now() + (rp.initialDelaySeconds||1)*1000;
  const liveAfter = Date.now() + (lp.initialDelaySeconds||1)*1000;
  pods.set(port, { id, service, digest, env, healthy, startTs: Date.now(), readyAfter, liveAfter });
  res.json({ id, pid: 0, port });
});

app.post('/kill', requireAuth, (req,res)=>{
  const { podId } = req.body;
  for (const [port, p] of pods.entries()) if (p.id===podId) pods.delete(port);
  res.json({ ok:true });
});

// Toggle health by service (for future scenarios)
app.post('/service/health', requireAuth, (req,res)=>{
  const { service, healthy } = req.body;
  for (const [port, p] of pods.entries()) if (p.service===service) p.healthy = !!healthy;
  res.json({ ok:true });
});

app.get('/probe', (req,res)=>{
  const port = parseInt(req.query.port||'0',10);
  const p = pods.get(port);
  if (!p) return res.status(404).end();
  const now = Date.now();
  const ready = p.healthy && now>=p.readyAfter;
  const live = p.healthy && now>=p.liveAfter;
  // combine: if not live -> 500; if live but not ready -> 503; if ready -> 200
  if (!live) return res.status(500).end('not live');
  if (!ready) return res.status(503).end('not ready');
  res.status(200).end('ok');
});

const PORT = parseInt(process.env.AGENT_PORT||'8070',10);
app.listen(PORT, ()=> console.log('Agent listening on :'+PORT));
