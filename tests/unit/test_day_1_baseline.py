from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.procurement import routes
from enterprise.procurement.routes import ComponentHealth, router

HEALTH_PATH = "/api/v1/enterprise/procurement/health"


async def _healthy_component() -> ComponentHealth:
    return ComponentHealth(status="ok", detail="test")


def test_procurement_health_is_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(routes, "_check_skyvern_core", lambda: ComponentHealth(status="ok", detail="test"))
    monkeypatch.setattr(routes, "_check_database", _healthy_component)
    monkeypatch.setattr(routes, "_check_redis", _healthy_component)
    monkeypatch.setattr(routes, "_check_minio", _healthy_component)
    monkeypatch.setattr(routes, "_check_browser", _healthy_component)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    response = TestClient(app).get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ready"] is True
    assert response.json()["skyvern_core"]["status"] == "ok"


def test_ready_health_reports_unavailable_component(monkeypatch) -> None:
    async def unavailable_database() -> ComponentHealth:
        return ComponentHealth(status="unavailable", detail="test")

    monkeypatch.setattr(routes, "_check_skyvern_core", lambda: ComponentHealth(status="ok", detail="test"))
    monkeypatch.setattr(routes, "_check_database", unavailable_database)
    monkeypatch.setattr(routes, "_check_redis", _healthy_component)
    monkeypatch.setattr(routes, "_check_minio", _healthy_component)
    monkeypatch.setattr(routes, "_check_browser", _healthy_component)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    response = TestClient(app).get(f"{HEALTH_PATH}?ready=true")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"]["status"] == "unavailable"


def test_skyvern_app_registers_enterprise_and_core_routes() -> None:
    from skyvern.forge.api_app import create_api_app

    app = create_api_app()
    paths = {route.path for route in app.routes}

    assert HEALTH_PATH in paths
    assert "/api/v1/enterprise/procurement/smoke-task" in paths
    assert "/v1/run/tasks/" in paths
    assert "/v1/run/workflows/" in paths
