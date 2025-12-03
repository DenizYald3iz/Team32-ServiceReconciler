from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"version": "v1", "message": "Hello from Service V1"}

@app.get("/health")
def health_check():
    # Yönetici (Manager) buraya istek atacak
    return {"status": "healthy", "version": "v1"}