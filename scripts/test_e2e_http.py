import httpx
import time
import json

BASE_URL = "http://localhost:8000"

def test_workflow():
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Health check
    res = client.get("/health")
    print(f"Health check: {res.status_code} - {res.json()}")
    assert res.status_code == 200

    # 2. Register application with submission data to trigger automatic certification
    unique_suffix = int(time.time())
    app_data = {
        "application_id": f"app-phase12-{unique_suffix}",
        "name": f"Phase 12 E2E Test App {unique_suffix}",
        "description": "Validation app for Phase 12 auto-certification",
        "version": "1.0.0",
        "commit_hash": f"commit-{unique_suffix}",
        "submission_id": f"sub-{unique_suffix}"
    }
    res = client.post("/api/v1/applications", json=app_data)
    print(f"Application registration response: {res.status_code} - {res.text}")
    assert res.status_code == 201
    app_json = res.json()
    app_id = app_json["application_id"]
    print(f"Registered App application_id: {app_id}, latest_certification_run_id: {app_json.get('latest_certification_run_id')}")

    # Wait for Celery worker to pick up and process certification run
    time.sleep(4)

    # 3. Check application status
    status_res = client.get(f"/api/v1/applications/{app_id}/status")
    print(f"Status check response: {status_res.status_code}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    print("Certification Status:", json.dumps(status_data, indent=2))

    # 4. Check publication status
    pub_res = client.get(f"/api/v1/applications/{app_id}/publication-status")
    print(f"Publication status response: {pub_res.status_code}")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    print("Publication Status:", json.dumps(pub_data, indent=2))

    # 5. Verify publication attempt is blocked when policy engine says NOT_READY
    pub_attempt = client.post(f"/api/v1/applications/{app_id}/publish", json={"environment": "production"})
    print(f"Publish attempt response: {pub_attempt.status_code} - {pub_attempt.text}")
    assert pub_attempt.status_code == 400

    # 6. Idempotency test: triggering certification for the same version and commit
    dup_cert_res = client.post(
        f"/api/v1/certifications",
        json={
            "application_id": app_id,
            "version": "1.0.0",
            "commit_hash": f"commit-{unique_suffix}",
            "submission_id": f"sub-{unique_suffix}",
            "idempotency_key": f"{app_id}:1.0.0:commit-{unique_suffix}"
        }
    )
    print(f"Duplicate trigger response: {dup_cert_res.status_code} - {dup_cert_res.text}")
    assert dup_cert_res.status_code == 202
    dup_json = dup_cert_res.json()
    assert dup_json["certification_id"] == status_data["latest_certification"]["certification_id"]
    print(f"Idempotency verified: Reused existing run {dup_json['certification_id']}")

    print("\n--- ALL API CHECKS PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    test_workflow()
