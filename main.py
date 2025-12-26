from fastapi import FastAPI
import docker
import time
import threading
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from monitor import check_service_health
import os

app = FastAPI(title="Dynamic Service Reconciler (Self-Healing)")

# --- AYARLAR ---
REGISTERED_SERVICES = {
    "service-v1": "http://localhost:8001/health"
}
# Servis Adı -> Konteyner Adı Eşleşmesi (Burası Çok Önemli)
CONTAINER_MAP = {
    "service-v1": "my-v1-container"
}
DB_NAME = "monitor.db"

# --- MAİL AYARLARI ---
# Not: GitHub'a atarken şifreni gizlemeyi unutma!
SENDER_EMAIL = "ahmetalicallar1@gmail.com"
SENDER_PASSWORD = "lklh xvtv fcut qtfq"
RECEIVER_EMAIL = "ahmetalicallar1@gmail.com"

service_last_status = {}

# --- MAİL GÖNDERME FONKSİYONU ---
def send_alert_email(service_name, msg_content, is_recovery=False, is_healing=False):
    """
    Duruma göre (Çökme, İyileşme, Tamir Başlangıcı) farklı mailler atar.
    """
    try:
        if is_healing:
            subject = f"🛠️ OTOMATİK TAMİR: {service_name} Yeniden Başlatılıyor"
            body_header = "Bilgilendirme,"
            status_icon = "🔧 DURUM: HEALING (İYİLEŞTİRME)"
            color_msg = "Sistem hatayı fark etti ve otomatik onarım başlattı."
        elif is_recovery:
            subject = f"✅ SİSTEM DÜZELDİ: {service_name} Tekrar Aktif"
            body_header = "Harika Haber,"
            status_icon = "🟢 DURUM: UP (AKTİF)"
            color_msg = "Otomatik onarım başarılı oldu veya servis geri geldi."
        else:
            subject = f"🚨 KRİTİK UYARI: {service_name} Çöktü!"
            body_header = "Dikkat,"
            status_icon = "🔴 DURUM: DOWN (ÇÖKTÜ)"
            color_msg = "Müdahale bekleniyor veya otomatik onarım denenecek."

        body = f"""
        {body_header}
        
        Dynamic Service Reconciler sistemi raporu:
        
        📍 Servis: {service_name}
        ⏰ Zaman: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        {status_icon}
        📝 Detay: {msg_content}
        ℹ️ Not: {color_msg}
        """

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, text)
        server.quit()
        return True
    except Exception as e:
        print(f"⚠️ Mail hatası: {e}")
        return False

# --- DOKTOR: OTOMATİK İYİLEŞTİRME (SELF-HEALING) ---
def attempt_recovery(service_name):
    """Bozuk konteyneri bulur ve restart eder"""
    container_name = CONTAINER_MAP.get(service_name)
    if not container_name:
        print(f"⚠️ Bilinmeyen konteyner: {service_name}")
        return False

    print(f"🔧 ONARIM BAŞLIYOR: {container_name} yeniden başlatılıyor...")
    # 'Tamir Başladı' maili at
    send_alert_email(service_name, "Otomatik onarım protokolü devreye girdi.", is_healing=True)
    
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        
        # Docker'a 'Restart' emri ver
        container.restart()
        
        # Konteynerin kendine gelmesi için 5-10 saniye bekle
        time.sleep(5)
        print(f"✨ ONARIM TAMAMLANDI: {container_name}")
        return True
    except Exception as e:
        print(f"❌ ONARIM BAŞARISIZ: {e}")
        return False

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            service_name TEXT,
            status TEXT,
            latency_ms REAL
        )
    ''')
    conn.commit()
    conn.close()

# --- ARKA PLAN ROBOTU ---
def background_monitor():
    print("👀 Self-Healing Modülü Aktif...")
    
    # Başlangıçta hepsini sağlam kabul et
    for name in REGISTERED_SERVICES:
        service_last_status[name] = True 

    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            for name, url in REGISTERED_SERVICES.items():
                start_time = time.time()
                is_alive, msg = check_service_health(url)
                end_time = time.time()
                latency = round((end_time - start_time) * 1000, 2)
                
                # --- AKILLI MANTIK ---
                if not is_alive:
                    # Servis ÖLÜ ise ve daha önce SAĞLAM idiyse
                    if service_last_status.get(name, True) == True:
                        print(f"🚨 ALARM: {name} gitti! Onarım deneniyor...")
                        
                        # 1. Çökme Maili At
                        send_alert_email(name, msg, is_recovery=False)
                        
                        # 2. Otomatik Tamir Et (Self-Healing)
                        attempt_recovery(name)
                        
                        service_last_status[name] = False 
                
                elif is_alive and service_last_status.get(name, True) == False:
                    # Servis DÜZELDİ ise
                    print(f"✅ İYİLEŞME: {name} geri geldi.")
                    # 3. İyileşme Maili At
                    send_alert_email(name, "Servis tekrar aktif.", is_recovery=True)
                    service_last_status[name] = True

                log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "INSERT INTO health_logs (timestamp, service_name, status, latency_ms) VALUES (?, ?, ?, ?)",
                    (log_time, name, "UP" if is_alive else "DOWN", latency)
                )

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Döngü Hatası: {e}")
            
        time.sleep(10) # 10 saniye bekle

@app.on_event("startup")
def startup_event():
    init_db()
    t = threading.Thread(target=background_monitor, daemon=True)
    t.start()

@app.get("/")
def home():
    return {"message": "Self-Healing Sistemi Aktif. Arkanıza yaslanın."}

@app.get("/history")
def get_history():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM health_logs ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return {"logs": rows}