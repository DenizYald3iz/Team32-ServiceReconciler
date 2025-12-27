from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import docker
import time
import threading
import sqlite3
import json
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# --- MONITOR ---
try:
    from monitor import check_service_health
except ImportError:
    def check_service_health(url):
        import requests
        try:
            r = requests.get(url, timeout=1.5)
            return (r.status_code == 200), "OK"
        except:
            return False, "TIMEOUT"

app = FastAPI(title="Kaos Mühendisliği ve Otonom Sistem v9.0")
security = HTTPBasic()

# --- GÜVENLİK ---
ADMIN_USER = "admin"
ADMIN_PASS = "secure123"

# --- AYARLAR ---
DB_NAME = "monitor.db"
SENDER_EMAIL = "ahmetalicallar1@gmail.com"
SENDER_PASSWORD = "lklh xvtv fcut qtfq"
RECEIVER_EMAIL = "ahmetalicallar1@gmail.com"

VERSIONS = ["v1", "v2", "v3"]
PORTS = {"v1": 8001, "v2": 8002, "v3": 8003}
current_v_index = 0

REGISTERED_SERVICES = {"Ana Servis": f"http://localhost:{PORTS['v1']}/health"}
CONTAINER_MAP = {"Ana Servis": "my-v1-container"}

failure_log = []
last_switch_time = 0
COOLDOWN = 15
FAIL_LIMIT = 5
system_status_msg = "Sistem Stabil"

# --- VERİTABANI ---
def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS health_logs (id INTEGER PRIMARY KEY, timestamp TEXT, service TEXT, status TEXT, latency REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY, timestamp TEXT, user TEXT, action TEXT, detail TEXT)')
    conn.close()

# --- GİRİŞ KONTROLÜ ---
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, ADMIN_USER) and secrets.compare_digest(credentials.password, ADMIN_PASS)):
        raise HTTPException(status_code=401, detail="Hatalı Giriş", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

# --- AUDIT LOG ---
def log_audit(user, action, detail):
    try:
        conn = get_db()
        conn.execute("INSERT INTO audit_logs (timestamp, user, action, detail) VALUES (?, ?, ?, ?)",
                     (datetime.now().strftime("%H:%M:%S"), user, action, detail))
        conn.commit(); conn.close()
    except: pass

# --- FAILOVER (SMART FALLBACK) ---
def execute_smart_failover():
    global current_v_index, last_switch_time, system_status_msg
    
    if time.time() - last_switch_time < COOLDOWN: return

    # V3'ten sonra V1'e dön (Loop)
    target_index = current_v_index + 1
    if target_index >= len(VERSIONS): target_index = 0
    
    current_v_index = target_index
    new_v = VERSIONS[current_v_index]
    new_port = PORTS[new_v]
    
    system_status_msg = f"KRİTİK HATA! {new_v.upper()} Geçişi Başlatıldı..."
    log_audit("SİSTEM (AI)", "FAILOVER", f"{new_v.upper()} sürümüne otomatik geçiş.")

    try:
        client = docker.from_env()
        client.images.build(path=f"./services/{new_v}", tag=f"service-{new_v}", rm=True)
        for v in VERSIONS:
            try: client.containers.get(f"my-{v}-container").remove(force=True)
            except: pass

        client.containers.run(f"service-{new_v}", detach=True, ports={'80/tcp': new_port}, name=f"my-{new_v}-container")
        REGISTERED_SERVICES["Ana Servis"] = f"http://localhost:{new_port}/health"
        CONTAINER_MAP["Ana Servis"] = f"my-{new_v}-container"
        last_switch_time = time.time()
        system_status_msg = f"BAŞARILI: {new_v.upper()} Aktif"
    except Exception as e:
        system_status_msg = f"Hata: {e}"

# --- MONITOR ---
def monitor_loop():
    global failure_log
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            for name, url in list(REGISTERED_SERVICES.items()):
                start_t = time.time()
                is_alive, _ = check_service_health(url)
                latency = round((time.time() - start_t) * 1000, 2)
                
                if not is_alive:
                    failure_log.append(time.time())
                    failure_log = [t for t in failure_log if t > time.time() - 10]
                    if len(failure_log) >= FAIL_LIMIT:
                        execute_smart_failover()
                        failure_log = []
                    else:
                        try: client.containers.get(CONTAINER_MAP[name]).restart()
                        except: pass
                
                cursor.execute("INSERT INTO health_logs (timestamp, service, status, latency) VALUES (?, ?, ?, ?)",
                               (datetime.now().strftime("%H:%M:%S"), name, "AKTİF" if is_alive else "KAPALI", latency))
            conn.commit(); conn.close()
        except: pass
        time.sleep(1.5)

@app.on_event("startup")
def startup():
    init_db()
    threading.Thread(target=monitor_loop, daemon=True).start()

# --- DASHBOARD (YÜKSEK KONTRAST) ---
@app.get("/", response_class=HTMLResponse)
def get_dashboard(username: str = Depends(get_current_username)):
    conn = get_db()
    logs = conn.execute("SELECT * FROM health_logs ORDER BY id DESC LIMIT 10").fetchall()
    audit = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    labels_json = json.dumps([l[1] for l in reversed(logs)])
    data_json = json.dumps([l[4] for l in reversed(logs)])
    
    rows = "".join([f"<tr style='border-bottom:1px solid #334155;'><td>{l[1]}</td><td><b style='color:{'#4ade80' if l[3]=='AKTİF' else '#f87171'}'>{l[3]}</b></td><td>{l[4]} ms</td></tr>" for l in logs])
    audit_rows = "".join([f"<tr style='border-bottom:1px solid #334155; font-size:0.9em;'><td style='color:#94a3b8'>{a[1]}</td><td style='color:#60a5fa'>{a[2]}</td><td style='color:#facc15'>{a[3]}</td><td>{a[4]}</td></tr>" for a in audit])
    ver = VERSIONS[current_v_index].upper()
    
    return f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>Güvenli Yönetim Paneli</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #020617; color: #f8fafc; font-family: 'Segoe UI', monospace; padding: 20px; }}
            .card-dark {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 20px; }}
            h5 {{ color: #ffffff; font-weight: 700; border-bottom: 2px solid #334155; padding-bottom: 10px; }}
            table {{ color: #ffffff !important; width: 100%; }}
            th {{ color: #94a3b8 !important; font-weight: 700; }}
            .btn-act {{ font-weight: bold; width: 100%; padding: 10px; margin-bottom: 10px; border:none; }}
            .btn-cpu {{ background: #eab308; color: black; }}
            .btn-corr {{ background: #ef4444; color: white; }}
            .btn-reset {{ background: #22c55e; color: white; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>🛡️ GÜVENLİ OTONOM SİSTEM <span class="badge bg-secondary fs-6">v9.0</span></h2>
                <div><span class="badge bg-primary">SÜRÜM: {ver}</span> <span class="badge bg-info">{system_status_msg}</span></div>
            </div>

            <div class="row">
                <div class="col-md-8">
                    <div class="card-dark">
                        <h5>📈 Gecikme Analizi (ms)</h5>
                        <canvas id="myChart" height="100"></canvas>
                    </div>
                    <div class="card-dark">
                        <h5 style="color:#facc15">🔒 Denetim Günlüğü (Audit Log)</h5>
                        <table><thead><tr><th>Saat</th><th>Kullanıcı</th><th>İşlem</th><th>Detay</th></tr></thead><tbody>{audit_rows}</tbody></table>
                    </div>
                </div>

                <div class="col-md-4">
                    <div class="card-dark">
                        <h5 style="color:#eab308">⚠️ KAOS LABORATUVARI</h5>
                        <p class="small text-muted">Sistemi test etmek için yapay sorunlar üretin.</p>
                        <a href="/chaos/cpu" class="btn btn-act btn-cpu">🐌 CPU YÜKLE (%100 LOAD)</a>
                        <a href="/chaos/corruption" class="btn btn-act btn-corr">💀 VERİ BOZULMASI (500 ERR)</a>
                        <a href="/chaos/reset" class="btn btn-act btn-reset">♻️ NORMALE DÖNDÜR</a>
                        <hr>
                        <a href="/crash" class="btn btn-act btn-danger">🔥 FİŞİ ÇEK (CRASH)</a>
                    </div>
                    <div class="card-dark">
                        <h5>📋 Sağlık Durumu</h5>
                        <table><thead><tr><th>Saat</th><th>Durum</th><th>ms</th></tr></thead><tbody>{rows}</tbody></table>
                    </div>
                </div>
            </div>
        </div>
        <script>
            new Chart(document.getElementById('myChart'), {{
                type: 'line',
                data: {{ labels: {labels_json}, datasets: [{{ label: 'Gecikme', data: {data_json}, borderColor: '#22d3ee', borderWidth: 2, tension: 0.3 }}] }},
                options: {{ animation: false, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#334155' }} }}, x: {{ display: false }} }} }}
            }});
            setTimeout(() => {{ window.location.reload(); }}, 3000);
        </script>
    </body>
    </html>
    """

# --- KAOS ENDPOINTLERİ ---
@app.get("/chaos/cpu")
def chaos_cpu(username: str = Depends(get_current_username)):
    log_audit(username, "KAOS", "CPU yüklemesi başlatıldı.")
    import requests
    try: requests.post(REGISTERED_SERVICES["Ana Servis"].replace("/health", "") + "/simulate/cpu/100", timeout=1)
    except: pass
    return HTMLResponse("<h1>🐌 YÜK BİNDİRİLDİ!</h1><script>setTimeout(()=>window.location.href='/', 1000);</script>")

@app.get("/chaos/corruption")
def chaos_corr(username: str = Depends(get_current_username)):
    log_audit(username, "KAOS", "Veri bozulması simüle edildi.")
    import requests
    try: requests.post(REGISTERED_SERVICES["Ana Servis"].replace("/health", "") + "/simulate/corruption", timeout=1)
    except: pass
    return HTMLResponse("<h1>💀 VERİ BOZULDU!</h1><script>setTimeout(()=>window.location.href='/', 1000);</script>")

@app.get("/chaos/reset")
def chaos_reset(username: str = Depends(get_current_username)):
    log_audit(username, "RESET", "Simülasyon sıfırlandı.")
    import requests
    try: requests.post(REGISTERED_SERVICES["Ana Servis"].replace("/health", "") + "/simulate/reset", timeout=1)
    except: pass
    return HTMLResponse("<h1>♻️ SIFIRLANDI!</h1><script>setTimeout(()=>window.location.href='/', 1000);</script>")

@app.get("/crash")
def crash_sim(username: str = Depends(get_current_username)):
    log_audit(username, "SABOTAJ", "Manuel çökertme yapıldı.")
    try:
        client = docker.from_env()
        global failure_log
        for _ in range(6): failure_log.append(time.time())
        for c in client.containers.list():
            if "my-v" in c.name: c.stop()
        return HTMLResponse("<h1 style='color:red;text-align:center;margin-top:20%'>🔥 SİSTEM ÇÖKERTİLDİ!</h1><script>setTimeout(()=>window.location.href='/', 2000);</script>")
    except Exception as e: return str(e)