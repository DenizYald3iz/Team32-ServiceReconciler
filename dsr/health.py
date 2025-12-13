from __future__ import annotations

import time

import httpx


def check_health(url: str, timeout_s: float = 2.0) -> tuple[bool, str, float | None]:
    """Call a service health endpoint.

    Expected JSON: {"status": "healthy"}.
    Returns (is_healthy, message, latency_ms).
    """
    start = time.time()
    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            resp = client.get(url)
        latency_ms = round((time.time() - start) * 1000.0, 2)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}", latency_ms
        try:
            data = resp.json()
        except Exception:
            return False, "Invalid JSON", latency_ms
        if isinstance(data, dict) and data.get("status") == "healthy":
            return True, "Healthy", latency_ms
        return False, f"Unhealthy payload: {data!r}", latency_ms
    except (httpx.ConnectError, httpx.ReadTimeout):
        latency_ms = round((time.time() - start) * 1000.0, 2)
        return False, "No response", latency_ms
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000.0, 2)
        return False, f"Error: {type(e).__name__}: {e}", latency_ms
