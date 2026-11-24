from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.core.config import Settings


@pytest.fixture
def database_lifecycle(monkeypatch):
    check = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(main_module, "check_database", check)
    monkeypatch.setattr(main_module, "close_database", close)
    monkeypatch.setattr(main_module, "recover_interrupted_scans", AsyncMock())
    return check, close


def test_health_and_database_lifecycle(database_lifecycle):
    check, close = database_lifecycle
    with TestClient(main_module.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        check.assert_awaited_once()
    close.assert_awaited_once()


def test_frontend_cors_preflight(database_lifecycle):
    with TestClient(main_module.app) as client:
        response = client.options(
            "/api/scans",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_unlisted_origin_is_not_allowed(database_lifecycle):
    with TestClient(main_module.app) as client:
        response = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in response.headers


def test_startup_failure_closes_pool_without_leaking_error(database_lifecycle):
    check, close = database_lifecycle
    check.side_effect = OSError("private connection details")
    with pytest.raises(RuntimeError, match="^Database startup check failed$"):
        with TestClient(main_module.app):
            pass
    close.assert_awaited_once()


def test_cors_origin_parsing():
    settings = Settings(
        _env_file=None, cors_origins="http://localhost:3000, , http://127.0.0.1:3000"
    )
    assert settings.allowed_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_database_driver_validation():
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        Settings(_env_file=None, database_url="sqlite:///invalid.db")
