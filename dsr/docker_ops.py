from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from .db import log_event
from .settings import settings


SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9\-]{0,62}$")
VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9\-\._]{0,63}$")


def validate_service_name(name: str) -> None:
    if not SERVICE_NAME_RE.match(name):
        raise ValueError(
            "Invalid service name. Use lowercase letters/numbers and hyphen, starting with a letter (max 63 chars)."
        )


def validate_version(version: str) -> None:
    if not VERSION_RE.match(version):
        raise ValueError("Invalid version string. Use letters/numbers and -._ (max 64 chars).")


def validate_health_path(path: str) -> None:
    # Security: keep it a path (not a full URL) to avoid turning the system into an SSRF proxy.
    if not path.startswith("/"):
        raise ValueError("health_path must start with '/'.")
    if "://" in path or ".." in path:
        raise ValueError("health_path must be a simple absolute path (no scheme, no '..').")


@dataclass(frozen=True)
class ContainerRef:
    id: str
    name: str


def _client() -> docker.DockerClient:
    return docker.from_env()


def docker_available() -> bool:
    try:
        c = _client()
        c.ping()
        return True
    except DockerException:
        return False


def ensure_network() -> None:
    if not docker_available():
        return
    c = _client()
    try:
        c.networks.get(settings.docker_network)
    except NotFound:
        c.networks.create(settings.docker_network, driver="bridge")
        log_event("INFO", f"Created docker network '{settings.docker_network}'.")


def create_service_container(
    service: str,
    version: str,
    image: str,
    internal_port: int,
    env: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> ContainerRef:
    """Create and start a container attached to the DSR network.

    Containers are labeled so we can re-discover them after restarts.
    """
    validate_service_name(service)
    validate_version(version)
    ensure_network()

    if not docker_available():
        raise RuntimeError("Docker is not available. Start Docker Desktop / docker daemon and try again.")

    rand = secrets.token_hex(3)
    name = f"dsr-{service}-{version}-{rand}"
    labels: dict[str, str] = {
        "dsr.service": service,
        "dsr.version": version,
    }

    c = _client()
    container = c.containers.run(
        image,
        command=command,
        detach=True,
        name=name,
        environment=env or {},
        network=settings.docker_network,
        labels=labels,
        # We do self-healing ourselves; keep Docker restart policy off to make behavior explicit.
        restart_policy={"Name": "no"},
    )

    log_event("INFO", f"Started container {name} from image {image}", service_name=service, version=version)
    return ContainerRef(id=container.id, name=name)


def remove_container(container_id: str, force: bool = True) -> None:
    if not docker_available():
        return
    c = _client()
    try:
        cont = c.containers.get(container_id)
        cont.remove(force=force)
    except NotFound:
        return


def list_containers(service: str | None = None, version: str | None = None) -> list[ContainerRef]:
    if not docker_available():
        return []
    c = _client()
    filters: dict[str, Any] = {"label": []}
    if service:
        filters["label"].append(f"dsr.service={service}")
    if version:
        filters["label"].append(f"dsr.version={version}")

    containers = c.containers.list(all=True, filters=filters)
    return [ContainerRef(id=x.id, name=x.name) for x in containers]


def container_is_running(container_id: str) -> bool:
    if not docker_available():
        return False
    c = _client()
    try:
        cont = c.containers.get(container_id)
        cont.reload()
        return cont.status == "running"
    except NotFound:
        return False


def container_http_base(container_name: str, internal_port: int) -> str:
    """HTTP base URL usable from within the same docker network."""
    return f"http://{container_name}:{int(internal_port)}"

