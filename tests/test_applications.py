"""Tests for Application API endpoints."""


def test_create_application(client):
    """POST /api/v1/applications should successfully create an application."""
    payload = {
        "application_id": "APP-1001",
        "name": "Research Agent",
        "description": "Autonomous deep research agent",
        "application_type": "AI_AGENT",
        "version": "1.0.0",
        "commit_hash": "abc1234",
    }
    response = client.post("/api/v1/applications", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["application_id"] == "APP-1001"
    assert data["name"] == "Research Agent"
    assert data["current_version"] == "1.0.0"
    assert data["application_type"] == "AI_AGENT"
    assert "id" in data
    assert "created_at" in data


def test_create_duplicate_application(client):
    """POST /api/v1/applications with duplicate ID must return 409 Conflict."""
    payload = {
        "application_id": "APP-DUP-1",
        "name": "First Instance",
        "version": "1.0.0",
    }
    res1 = client.post("/api/v1/applications", json=payload)
    assert res1.status_code == 201

    # Second creation with identical application_id
    res2 = client.post("/api/v1/applications", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert "error" in data
    assert data["error"]["code"] == "APPLICATION_ALREADY_EXISTS"


def test_get_application(client):
    """GET /api/v1/applications/{id} should return existing application."""
    payload = {
        "application_id": "APP-2002",
        "name": "Data Processor",
        "version": "2.1.0",
    }
    client.post("/api/v1/applications", json=payload)

    response = client.get("/api/v1/applications/APP-2002")
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "APP-2002"
    assert data["name"] == "Data Processor"
    assert data["current_version"] == "2.1.0"


def test_get_invalid_application(client):
    """GET /api/v1/applications/{id} for non-existent app must return 404."""
    response = client.get("/api/v1/applications/APP-NON-EXISTENT")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "APPLICATION_NOT_FOUND"


def test_list_applications(client):
    """GET /api/v1/applications should list registered applications."""
    for i in range(3):
        client.post("/api/v1/applications", json={
            "application_id": f"APP-LIST-{i}",
            "name": f"App {i}",
            "version": "1.0.0",
        })

    response = client.get("/api/v1/applications?skip=0&limit=10")
    assert response.status_code == 200
    apps = response.json()
    assert len(apps) >= 3


def test_application_status_without_runs(client):
    """GET /api/v1/applications/{id}/status returns null latest_certification before runs."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-STATUS-0",
        "name": "Fresh App",
        "version": "1.0.0",
    })

    response = client.get("/api/v1/applications/APP-STATUS-0/status")
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "APP-STATUS-0"
    assert data["latest_certification"] is None
