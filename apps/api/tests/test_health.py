from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "api"}


def test_readiness_reports_all_foundation_components(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["components"]["database"]["status"] == "healthy"
    assert set(payload["components"]) == {
        "api",
        "database",
        "redis",
        "object_storage",
        "worker",
    }
