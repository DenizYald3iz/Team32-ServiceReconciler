from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"version": "v3", "message": "BU FINAL SURUMUDUR (V3)! Maksimum stabilite saglandi."}

@app.get("/health")
def health():
    return {"status": "healthy", "version": "3.0"}