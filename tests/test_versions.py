"""Tests for Application Versions model and endpoints."""


def test_create_and_list_application_versions(client):
    """Register application and manage multiple versions."""
    # Initial application registration creates version 1.0.0 automatically
    client.post("/api/v1/applications", json={
        "application_id": "APP-MULTI-VER",
        "name": "Versioned Agent",
        "version": "1.0.0",
        "commit_hash": "commit-001",
    })

    # List versions: initial version 1.0.0 should be present
    res_list1 = client.get("/api/v1/applications/APP-MULTI-VER/versions")
    assert res_list1.status_code == 200
    data1 = res_list1.json()
    assert data1["application_id"] == "APP-MULTI-VER"
    assert data1["total_versions"] == 1
    assert data1["versions"][0]["version"] == "1.0.0"

    # Add version 1.1.0
    res_v11 = client.post("/api/v1/applications/APP-MULTI-VER/versions", json={
        "version": "1.1.0",
        "commit_hash": "commit-002",
        "submission_id": "SUB-101",
    })
    assert res_v11.status_code == 201
    assert res_v11.json()["version"] == "1.1.0"
    assert res_v11.json()["submission_id"] == "SUB-101"

    # Add version 1.2.0
    res_v12 = client.post("/api/v1/applications/APP-MULTI-VER/versions", json={
        "version": "1.2.0",
        "commit_hash": "commit-003",
        "submission_id": "SUB-102",
    })
    assert res_v12.status_code == 201

    # Verify all 3 versions listed
    res_list2 = client.get("/api/v1/applications/APP-MULTI-VER/versions")
    assert res_list2.status_code == 200
    data2 = res_list2.json()
    assert data2["total_versions"] == 3
    versions = [v["version"] for v in data2["versions"]]
    assert "1.0.0" in versions
    assert "1.1.0" in versions
    assert "1.2.0" in versions


def test_duplicate_version_rejected(client):
    """Registering an existing version for the same application must return 409 Conflict."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-VER-DUP",
        "name": "Duplicate Version Test",
        "version": "1.0.0",
    })

    # Attempt to create duplicate 1.0.0
    res = client.post("/api/v1/applications/APP-VER-DUP/versions", json={
        "version": "1.0.0",
    })
    assert res.status_code == 409
    data = res.json()
    assert data["error"]["code"] == "APPLICATION_VERSION_ALREADY_EXISTS"


def test_versions_for_unknown_application(client):
    """Listing or adding versions for non-existent application returns 404."""
    res_get = client.get("/api/v1/applications/APP-NON-EXISTENT-X/versions")
    assert res_get.status_code == 404
    assert res_get.json()["error"]["code"] == "APPLICATION_NOT_FOUND"

    res_post = client.post("/api/v1/applications/APP-NON-EXISTENT-X/versions", json={
        "version": "1.0.0",
    })
    assert res_post.status_code == 404
    assert res_post.json()["error"]["code"] == "APPLICATION_NOT_FOUND"
