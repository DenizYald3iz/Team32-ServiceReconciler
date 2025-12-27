from fastapi import FastAPI, HTTPException
import time

app = FastAPI()

APP_STATE = {"version": "v2", "cpu_load": 0, "is_corrupted": False}

@app.get("/")
def read_root():
    if APP_STATE["cpu_load"] > 0: time.sleep(APP_STATE["cpu_load"] / 20.0)
    if APP_STATE["is_corrupted"]: raise HTTPException(status_code=500, detail="DATA_ERR")
    return {"version": "v2", "message": "Servis V2 Aktif", "load": f"%{APP_STATE['cpu_load']}"}

@app.get("/health")
def health_check():
    if APP_STATE["is_corrupted"]: raise HTTPException(status_code=503, detail="Corrupted")
    if APP_STATE["cpu_load"] > 50: time.sleep(2)
    return {"status": "healthy", "version": "v2"}

@app.post("/simulate/cpu/{level}")
def set_cpu(level: int):
    APP_STATE["cpu_load"] = level
    return {"msg": "V2 CPU Yuku Arttirildi."}

@app.post("/simulate/corruption")
def corrupt():
    APP_STATE["is_corrupted"] = True
    return {"msg": "V2 Verisi Bozuldu."}

@app.post("/simulate/reset")
def reset():
    APP_STATE["cpu_load"] = 0
    APP_STATE["is_corrupted"] = False
    return {"msg": "V2 Normale Dondu."}