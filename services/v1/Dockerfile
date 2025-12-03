# Hafif bir Python sürümü kullan
FROM python:3.9-slim

# Çalışma klasörünü ayarla
WORKDIR /app

# Gerekli kütüphaneyi kur (Sadece FastAPI ve Uvicorn)
RUN pip install fastapi uvicorn

# Kodumuzu içeri kopyala
COPY app.py .

# Uygulamayı başlat
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]