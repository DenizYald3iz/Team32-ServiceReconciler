from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Core
    db_path: str = os.getenv("DSR_DB_PATH", "dsr.db")
    poll_interval_s: int = _env_int("DSR_POLL_INTERVAL_S", 5)
    docker_network: str = os.getenv("DSR_DOCKER_NETWORK", "dsr")
    gateway_timeout_s: int = _env_int("DSR_GATEWAY_TIMEOUT_S", 10)

    # Email alerting (optional)
    enable_email: bool = _env_bool("DSR_ENABLE_EMAIL", False)
    smtp_host: str = os.getenv("DSR_SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = _env_int("DSR_SMTP_PORT", 587)
    smtp_user: str | None = os.getenv("DSR_SMTP_USER")
    smtp_password: str | None = os.getenv("DSR_SMTP_PASSWORD")
    email_from: str | None = os.getenv("DSR_EMAIL_FROM")
    email_to: str | None = os.getenv("DSR_EMAIL_TO")

    # Safety knobs
    # Prevent the API from being used as an arbitrary HTTP proxy.
    allow_external_targets: bool = _env_bool("DSR_ALLOW_EXTERNAL_TARGETS", False)


settings = Settings()
