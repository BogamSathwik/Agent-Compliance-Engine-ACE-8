"""Tests for health and readiness endpoints."""

from unittest.mock import patch


def test_health_endpoint(client):
    """GET /health should return 200 and application metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app" in data
    assert "version" in data


def test_readiness_endpoint_success(client):
    """GET /health/ready should return 200 when database connectivity succeeds."""
    with patch("app.api.health.check_db_connectivity", return_value=True):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert response.json()["database"] == "connected"


def test_readiness_endpoint_failure(client):
    """GET /health/ready should return 503 when database is unreachable."""
    with patch("app.api.health.check_db_connectivity", return_value=False):
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert response.json()["database"] == "disconnected"
