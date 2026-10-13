from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_post_without_key_is_401(client: TestClient) -> None:
    resp = client.post("/probe", json={"url": "https://example.com"})
    assert resp.status_code == 401
    assert resp.json() == {
        "error": {"code": "unauthorized", "message": "missing or invalid API key"}
    }


def test_post_with_wrong_key_is_401(client: TestClient) -> None:
    resp = client.post("/probe", json={}, headers={"X-API-Key": "nope"})
    assert resp.status_code == 401


def test_bearer_header_is_accepted(client: TestClient) -> None:
    # Auth passes, then the empty body fails validation: 422, not 401.
    resp = client.post("/probe", json={}, headers={"Authorization": "Bearer test-key"})
    assert resp.status_code == 422


def test_x_api_key_is_accepted(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post("/probe", json={}, headers=auth_headers)
    assert resp.status_code == 422


def test_empty_api_key_disables_auth(tmp_path, fake_binaries: None) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, api_key="")
    with TestClient(create_app(settings)) as client:
        assert client.post("/probe", json={}).status_code == 422


def test_not_found_uses_error_envelope(client: TestClient) -> None:
    resp = client.get("/nope")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]
