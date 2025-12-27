import nodemailer from 'nodemailer';

function parseBool(v, def = false) {
  if (v === undefined || v === null || v === '') return def;
  const s = String(v).trim().toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on'].includes(s)) return true;
  if (['0', 'false', 'no', 'n', 'off'].includes(s)) return false;
  return def;
}

function parseIntEnv(name, def) {
  const raw = process.env[name];
  const n = parseInt(String(raw ?? ''), 10);
  return Number.isFinite(n) ? n : def;
}

function listEnv(name) {
  // Split comma-separated list, trim, drop empties, and de-duplicate.
  // Duplicate recipients can otherwise look like "the same email was sent twice".
  const items = String(process.env[name] || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return [...new Set(items)];
}

export function mailConfig() {
  const host = process.env.SMTP_HOST || '';
  const port = parseIntEnv('SMTP_PORT', 587);
  const secure = parseBool(process.env.SMTP_SECURE, port === 465);
  const user = process.env.SMTP_USER || '';
  const pass = process.env.SMTP_PASS || '';
  const from = process.env.EMAIL_FROM || 'perfect-system@localhost';
  const to = listEnv('EMAIL_TO');
  const subjectPrefix = process.env.EMAIL_SUBJECT_PREFIX || '[Perfect System] ';
  const uiUrl = process.env.PUBLIC_UI_URL || '';
  const timeoutMs = parseIntEnv('SMTP_TIMEOUT_MS', 8000);
  return { host, port, secure, user, pass, from, to, subjectPrefix, uiUrl, timeoutMs };
}

let transporter = null;
let transporterKey = '';

export function mailEnabled() {
  const cfg = mailConfig();
  return Boolean(cfg.host) && cfg.to.length > 0;
}

function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '';
  const sec = Math.floor(ms / 1000);
  const s = sec % 60;
  const min = Math.floor(sec / 60);
  const m = min % 60;
  const h = Math.floor(min / 60);
  const parts = [];
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(' ');
}

function getTransporter() {
  const cfg = mailConfig();
  const key = `${cfg.host}|${cfg.port}|${cfg.secure}|${cfg.user}`;
  if (transporter && transporterKey === key) return transporter;

  transporterKey = key;
  transporter = nodemailer.createTransport({
    host: cfg.host,
    port: cfg.port,
    secure: cfg.secure,
    ...(cfg.user || cfg.pass ? { auth: { user: cfg.user, pass: cfg.pass } } : {}),
  });
  return transporter;
}

async function withTimeout(promise, ms) {
  if (!Number.isFinite(ms) || ms <= 0) return promise;
  let t;
  const timeout = new Promise((_, rej) => {
    t = setTimeout(() => rej(new Error('smtp timeout')), ms);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(t);
  }
}

export async function sendServiceAlert({ service, status, desired, ready, digest, whenTs, downtimeMs }) {
  if (!mailEnabled()) return { ok: false, skipped: true, reason: 'mail not configured' };
  const cfg = mailConfig();
  const whenIso = new Date(whenTs || Date.now()).toISOString();
  const subject = `${cfg.subjectPrefix}${service} is ${status}`;

  const lines = [
    `Service: ${service}`,
    `Status: ${status}`,
    `Desired replicas: ${desired}`,
    `Ready replicas: ${ready}`,
    `Digest: ${digest || '(unknown)'}`,
    `Time: ${whenIso}`,
  ];
  if (status === 'UP' && Number.isFinite(downtimeMs) && downtimeMs >= 0) {
    lines.push(`Downtime: ${formatDuration(downtimeMs)}`);
  }
  if (cfg.uiUrl) lines.push(`UI: ${cfg.uiUrl}`);
  const text = lines.join('\n');

  const info = await withTimeout(
    getTransporter().sendMail({
      from: cfg.from,
      to: cfg.to.join(', '),
      subject,
      text,
    }),
    cfg.timeoutMs
  );
  return { ok: true, info };
}
