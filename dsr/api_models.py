from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterVersionRequest(BaseModel):
    service: str = Field(..., description="Logical service name (dns-safe)")
    version: str = Field(..., description="Version label, e.g. v1, v2")
    image: str = Field(..., description="Docker image (name:tag)")
    internal_port: int = Field(..., ge=1, le=65535, description="Container port the service listens on")
    health_path: str = Field("/health", description="Health endpoint path")
    replicas: int = Field(1, ge=1, le=50)
    weight: int = Field(100, ge=0, le=100, description="Routing weight (percentage)")
    state: str = Field("active", description="active|candidate|retired")


class ScaleRequest(BaseModel):
    replicas: int = Field(..., ge=0, le=100)


class WeightRequest(BaseModel):
    weight: int = Field(..., ge=0, le=100)


class RolloutRequest(BaseModel):
    to_version: str
    image: str
    internal_port: int = Field(..., ge=1, le=65535)
    health_path: str = "/health"
    replicas: int = Field(1, ge=1, le=50)

    canary_weight: int = Field(10, ge=0, le=100)
    step_percent: int = Field(25, ge=1, le=100)
    step_interval_s: int = Field(15, ge=1, le=3600)
    auto: bool = True
    max_wait_s: int = Field(120, ge=10, le=3600)
