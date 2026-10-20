"""Users' full names: required for new accounts, editable, searchable, and sent to systems as "name"."""
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.security import signing_keys
from test_sso_flow import REDIRECT, authorize, first_sign_in, pkce


def test_full_name_is_required_trimmed_editable_and_searchable(client: TestClient):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    base = {"username": "name.thida", "email": "name.thida@pahtama.com", "password": "name-temp-1"}
    assert client.post("/api/admin/users", json=base).status_code == 422  # no full name
    assert client.post("/api/admin/users", json={**base, "full_name": "   "}).status_code == 422  # blank
    u = client.post("/api/admin/users", json={**base, "full_name": "  Mya Thida "}).json()
    try:
        assert u["full_name"] == "Mya Thida"
        assert [x["username"] for x in client.get("/api/admin/users?q=thida").json()] == ["name.thida"]
        assert client.get("/api/admin/users?q=Mya").json()[0]["full_name"] == "Mya Thida"  # by name, not username
        assert client.patch(f"/api/admin/users/{u['id']}", json={"full_name": ""}).status_code == 422
        assert client.patch(f"/api/admin/users/{u['id']}", json={"full_name": "Mya Thida Aung"}).json()["full_name"] == "Mya Thida Aung"
    finally:
        client.delete(f"/api/admin/users/{u['id']}")


def test_tokens_and_userinfo_carry_the_full_name(client: TestClient):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    system = client.post("/api/admin/applications", json={"name": "Name Sys", "redirect_uris": [REDIRECT]}).json()
    role = client.post(f"/api/admin/applications/{system['id']}/roles", json={"name": "user"}).json()
    u = client.post("/api/admin/users", json={
        "username": "name.ko", "full_name": "Ko Ko Aung", "email": "name.ko@pahtama.com", "password": "name-temp-1"}).json()
    client.put(f"/api/admin/users/{u['id']}/roles", json={"role_ids": [role["id"]]})
    try:
        with TestClient(app) as browser:
            first_sign_in(browser, "name.ko", "name-temp-1")
            verifier, challenge = pkce()
            loc = authorize(browser, system["client_id"], challenge).headers["location"]
            code = parse_qs(urlparse(loc).query)["code"][0]
        tokens = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier,
        }, auth=(system["client_id"], system["client_secret"])).json()
        for t in (tokens["access_token"], tokens["id_token"]):
            claims = signing_keys.verify(t, audience=system["client_id"])
            assert claims["name"] == "Ko Ko Aung" and claims["preferred_username"] == "name.ko"
        info = client.get("/oauth/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
        assert info["name"] == "Ko Ko Aung"
    finally:
        client.delete(f"/api/admin/users/{u['id']}")
        client.delete(f"/api/admin/applications/{system['id']}")
