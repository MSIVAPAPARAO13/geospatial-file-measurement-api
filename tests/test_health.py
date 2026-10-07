from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)


def test_health_check_returns_200_and_expected_payload():
    """Verify GET /health returns 200 OK and valid status metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == settings.PROJECT_NAME
    assert data["version"] == settings.VERSION
