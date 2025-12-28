import base64
import importlib.util
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient


def _import_main_module(project_root):
    """Import main.py as a module without requiring it to be installed as a package."""
    main_path = os.path.join(project_root, "main.py")
    spec = importlib.util.spec_from_file_location("service_reconciler_main", main_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _basic_auth(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_dashboard_requires_basic_auth(tmp_path):
    project_root = os.path.dirname(os.path.dirname(__file__))
    main = _import_main_module(project_root)

    # Use an isolated sqlite db for tests
    main.DB_NAME = str(tmp_path / "test.db")

    # Avoid the background monitor thread doing network/docker work
    main.monitor_loop = lambda: None

    with TestClient(main.app) as client:
        # No auth -> 401
        r = client.get("/")
        assert r.status_code == 401

        # Correct auth -> 200 and HTML
        r = client.get("/", headers=_basic_auth(main.ADMIN_USER, main.ADMIN_PASS))
        assert r.status_code == 200
        assert "<html" in r.text.lower()


def test_log_audit_writes_row(tmp_path):
    project_root = os.path.dirname(os.path.dirname(__file__))
    main = _import_main_module(project_root)

    main.DB_NAME = str(tmp_path / "audit.db")
    main.init_db()
    main.log_audit("tester", "UNIT_TEST", "hello")

    conn = sqlite3.connect(main.DB_NAME)
    rows = conn.execute("SELECT user, action, detail FROM audit_logs ORDER BY id DESC LIMIT 1").fetchall()
    conn.close()

    assert rows, "audit_logs should have at least one row"
    assert rows[0][0] == "tester"
    assert rows[0][1] == "UNIT_TEST"
    assert rows[0][2] == "hello"


def test_check_service_health_ok_and_down(monkeypatch, tmp_path):
    project_root = os.path.dirname(os.path.dirname(__file__))
    main = _import_main_module(project_root)

    class _Resp:
        status_code = 200

    def fake_get_ok(url, timeout=1):
        return _Resp()

    def fake_get_fail(url, timeout=1):
        raise TimeoutError("boom")

    monkeypatch.setattr(main, "requests", None, raising=False)  # make sure we don't rely on global requests

    # main.check_service_health imports requests inside function, so patch sys.modules
    import types, sys
    req = types.ModuleType("requests")
    req.get = fake_get_ok
    sys.modules["requests"] = req

    ok, msg = main.check_service_health("http://example")
    assert ok is True
    assert msg == "OK"

    req.get = fake_get_fail
    ok, msg = main.check_service_health("http://example")
    assert ok is False
    assert msg == "BAĞLANTI YOK"
