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

app = FastAPI(title="Dynamic Service Reconciler (Mail Alert)")

# --- AYARLAR ---
REGISTERED_SERVICES = {
    "service-v1": "http://localhost:8001/health"
}
DB_NAME = "monitor.db"

# --- MAİL AYARLARI  ---
SENDER_EMAIL = "*****@gmail.com"      
SENDER_PASSWORD = "**** **** **** ****"    
RECEIVER_EMAIL = "ahmetalicallar1@gmail.com"    

# Spam engellemek için son durumu hafızada tutuyoruz
service_last_status = {}  

# --- MAİL GÖNDERME FONKSİYONU ---
def send_alert_email(service_name, msg_content, is_recovery=False):
    """
    Servis çöktüğünde veya düzeldiğinde mail atar.
    is_recovery=True ise 'Düzeldi' maili atar.
    """
    try:
        if is_recovery:
            subject = f"✅ SİSTEM DÜZELDİ: {service_name} Tekrar Aktif"
            body_header = "Kanaryalar kurtuldu,"
            status_icon = "🟢 DURUM: UP (AKTİF)"
            color_msg = "Sistem kendi kendini toparladı veya manuel başlatıldı."
        else:
            subject = f"🚨 KRİTİK UYARI: {service_name} Çöktü!"
            body_header = "Biz kanarya sevenler derneğinden geliyoruz,"
            status_icon = "🔴 DURUM: DOWN (ÇÖKTÜ)"
            color_msg = "Lütfen acil müdahale ediniz."

        body = f"""
        {body_header}
        
        Dynamic Service Reconciler sistemi bir durum değişikliği tespit etti.
        
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
        
        print(f"📧 {'İyileşme' if is_recovery else 'Uyarı'} maili gönderildi: {RECEIVER_EMAIL}")
        return True
    except Exception as e:
        print(f"⚠️ Mail gönderilemedi: {e}")
        return False

# --- VERİTABANI KURULUMU ---
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

# --- ARKA PLAN ROBOTU ) ---
def background_monitor():
    print("👀 İzleme ve Bildirim sistemi başlatıldı...")
    
    # 1. BAŞLANGIÇ DURUMLARINI KAYDET 
    for name in REGISTERED_SERVICES:
        service_last_status[name] = True 

    # 2. SONSUZ DÖNGÜ
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            for name, url in REGISTERED_SERVICES.items():
                start_time = time.time()
                is_alive, msg = check_service_health(url)
                end_time = time.time()
                latency = round((end_time - start_time) * 1000, 2)
                
                # --- BİLDİRİM MANTIĞI ---
                
                # SENARYO 1: Servis ÇÖKTÜ 
             
                if not is_alive and service_last_status.get(name, True) == True:
                    print(f"🚨 ALARM: {name} çöktü! Mail atılıyor...")
                    send_alert_email(name, msg, is_recovery=False)
                    service_last_status[name] = False 
                
                # SENARYO 2: Servis DÜZELDİ 
                elif is_alive and service_last_status.get(name, True) == False:
                    print(f"✅ İYİLEŞME: {name} tekrar ayağa kalktı. Mail atılıyor...")
                    send_alert_email(name, "Servis tekrar sağlık kontrolüne cevap veriyor.", is_recovery=True)
                    service_last_status[name] = True

           
                log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
           
                cursor.execute(
                    "INSERT INTO health_logs (timestamp, service_name, status, latency_ms) VALUES (?, ?, ?, ?)",
                    (log_time, name, "UP" if is_alive else "DOWN", latency)
                )
                
             
                if not is_alive:
                     print(f"[{log_time}] {name}: DOWN ❌")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"⚠️ Arka plan döngüsünde hata: {e}")
            
        time.sleep(10) # 10 Saniyede bir kontrol

@app.on_event("startup")
def startup_event():
    init_db()
    t = threading.Thread(target=background_monitor, daemon=True)
    t.start()

@app.get("/")
def home():
    return {"message": "Sistem Aktif. Loglar ve Mail bildirimleri çalışıyor."}

@app.get("/history")
def get_history():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM health_logs ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return {"logs": rows}