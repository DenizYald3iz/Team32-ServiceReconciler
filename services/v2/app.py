from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {"version": "v2", "message": "Hello from Service V2"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "v2"}


@app.get("/version")
def version():
    return {"version": "v2"}
