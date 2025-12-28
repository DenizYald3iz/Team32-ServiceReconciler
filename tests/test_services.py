import pytest
from fastapi.testclient import TestClient

from services.v1.app import app as v1_app, APP_STATE as v1_state
from services.v2.app import app as v2_app, APP_STATE as v2_state
from services.v3.app import app as v3_app


@pytest.mark.parametrize(
    "app,state,version_label",
    [
        (v1_app, v1_state, "v1"),
        (v2_app, v2_state, "v2"),
    ],
)
def test_cpu_simulation_and_reset(app, state, version_label):
    client = TestClient(app)

    # Start clean
    client.post("/simulate/reset")
    assert state["cpu_load"] == 0
    assert state["is_corrupted"] is False

    r = client.post("/simulate/cpu/10")
    assert r.status_code == 200
    assert state["cpu_load"] == 10

    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == version_label
    assert "%10" in body["load"]

    r = client.post("/simulate/reset")
    assert r.status_code == 200
    assert state["cpu_load"] == 0
    assert state["is_corrupted"] is False


@pytest.mark.parametrize(
    "app,state",
    [
        (v1_app, v1_state),
        (v2_app, v2_state),
    ],
)
def test_corruption_affects_root_and_health(app, state):
    client = TestClient(app)

    client.post("/simulate/reset")
    r = client.post("/simulate/corruption")
    assert r.status_code == 200
    assert state["is_corrupted"] is True

    r = client.get("/")
    assert r.status_code == 500
    assert r.json()["detail"] == "DATA_ERR"

    r = client.get("/health")
    assert r.status_code == 503

    client.post("/simulate/reset")
    r = client.get("/health")
    assert r.status_code == 200


def test_v3_root_and_health():
    client = TestClient(v3_app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["version"] == "v3"

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
