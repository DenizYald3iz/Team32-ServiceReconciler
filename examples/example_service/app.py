from __future__ import annotations

import os
import random
import time

from fastapi import FastAPI


VERSION = os.getenv("VERSION", "dev")
FAIL_RATE = float(os.getenv("FAIL_RATE", "0"))  # 0..1

app = FastAPI(title=f"Example Service {VERSION}")


@app.get("/health")
def health() -> dict[str, str]:
    # Optional fault injection to demo self-healing/rollouts.
    if FAIL_RATE > 0 and random.random() < FAIL_RATE:
        time.sleep(3)
    return {"status": "healthy"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": VERSION}
