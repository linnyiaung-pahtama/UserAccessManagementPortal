"""Admins can change a user's username (routers/users.py)."""
from fastapi.testclient import TestClient

from app.main import app


def test_admin_renames_a_user(client: TestClient):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    new = lambda u: client.post("/api/admin/users", json={  # noqa: E731
        "username": u, "full_name": f"Test {u}", "email": f"{u}@pahtama.com", "password": "rename-temp-1"}).json()
    mya, taken = new("ren.mya"), new("ren.taken")
    try:
        uid = mya["id"]
        assert client.patch(f"/api/admin/users/{uid}", json={"username": "bad name!"}).status_code == 422
        assert client.patch(f"/api/admin/users/{uid}", json={"username": "ren.taken"}).status_code == 409
        assert client.patch(f"/api/admin/users/{uid}", json={"username": "REN.TAKEN"}).status_code == 409  # capitals
        assert client.post("/api/admin/users", json={  # same rule when creating
            "username": "Ren.Mya", "full_name": "X", "email": "x.ren@pahtama.com", "password": "rename-temp-1"}).status_code == 409

        renamed = client.patch(f"/api/admin/users/{uid}", json={"username": "ren.mya.t"}).json()
        assert renamed["username"] == "ren.mya.t"
        assert client.patch(f"/api/admin/users/{uid}", json={"username": "Ren.Mya.T"}).json()["username"] == "Ren.Mya.T"  # own name, other case

        audit = [e for e in client.get("/api/admin/audit").json() if e["action"] == "user.update" and e["target"] == "ren.mya.t"]
        assert audit and "username was ren.mya" in audit[0]["detail"]

        # They sign in with the new name; the old one no longer works.
        with TestClient(app) as browser:
            assert browser.post("/api/auth/login", json={"username": "ren.mya", "password": "rename-temp-1"}).status_code == 401
            assert browser.post("/api/auth/login", json={"username": "Ren.Mya.T", "password": "rename-temp-1"}).status_code == 200
    finally:
        for u in (mya, taken):
            client.delete(f"/api/admin/users/{u['id']}")
