import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(ingestion_app):
    return TestClient(ingestion_app)


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "LOCAL_ONLY"}

def test_path_traversal_protection(client):
    # Test path traversal attempts
    bad_paths = [
        "../file.pdf",
        "..\\file.pdf",
        "/absolute/file.pdf",
        "\\absolute\\file.pdf",
        "C:\\outside\\file.pdf",
        "file\0.pdf"
    ]
    
    for bad_path in bad_paths:
        files = {"files": ("test.txt", b"content", "text/plain")}
        data = {"paths": [bad_path]}
        response = client.post("/api/ingest", files=files, data=data)
        assert response.status_code == 400
        assert "Invalid path" in response.text or "Path traversal" in response.text

def test_normal_upload(client):
    files = {"files": ("test.txt", b"content", "text/plain")}
    data = {"paths": ["valid/path/test.txt"]}
    response = client.post("/api/ingest", files=files, data=data)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "completed"
    assert res_json["discovered"] == 1
