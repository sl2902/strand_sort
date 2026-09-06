from strand_sort.config import settings


def test_config_reports_local_upload_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "local")
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json() == {"upload_mode": "local"}


def test_config_reports_presigned_upload_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json() == {"upload_mode": "presigned"}
