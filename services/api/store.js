import fs from 'fs';
import path from 'path';

export const STORE_PATH = process.env.STORE_PATH || path.join(process.cwd(), 'data', 'state.json');

function ensureStore() {
  const dir = path.dirname(STORE_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(STORE_PATH)) {
    const init = { services: {}, pods: {}, events: [], metrics: { restarts: {}, readyBySvc: {} }, alerts: {}, explain: false };
    fs.writeFileSync(STORE_PATH, JSON.stringify(init, null, 2));
  }
}
export function readStore() { ensureStore(); return JSON.parse(fs.readFileSync(STORE_PATH,'utf8')); }
export function writeStore(state) {
  const tmp = STORE_PATH + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, STORE_PATH);
}
export function now() { return Date.now(); }
export function recordEvent(state, level, svc, pod, msg, explain) {
  state.events.push({ ts: now(), level, svc: svc || null, pod: pod || null, msg, explain: explain || null });
}
