"""A user created by an admin is emailed their sign-in details (routers/users.py)."""
from fastapi.testclient import TestClient

import app.routers.users as users


def test_new_user_is_emailed_their_sign_in_details(client: TestClient, monkeypatch):
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(users, "send_mail", lambda to, subject, body: sent.append((to, subject, body)) or True)
    monkeypatch.setattr(users, "mail_configured", lambda: True)

    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "mail.min", "full_name": "Test mail.min", "email": "Mail.Min@pahtama.com", "password": "first-pass-1"}).json()
    try:
        assert created["emailed"] is True
        assert len(sent) == 1
        to, subject, body = sent[0]
        assert to == ["mail.min@pahtama.com"] and subject == "Your Access Portal account"
        assert "Username: mail.min" in body and "Email: mail.min@pahtama.com" in body
        assert "Temporary password: first-pass-1" in body and "/login" in body

        # Other user edits send nothing.
        client.patch(f"/api/admin/users/{created['id']}", json={"is_admin": False})
        assert len(sent) == 1
    finally:
        client.delete(f"/api/admin/users/{created['id']}")


def test_new_user_with_system_access_gets_the_links(client: TestClient, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(users, "send_mail", lambda to, subject, body: sent.append(body) or True)
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200

    def system(name, home_url, active=True):
        a = client.post("/api/admin/applications", json={
            "name": name, "redirect_uris": ["http://mail.local/cb"], "home_url": home_url}).json()
        role = client.post(f"/api/admin/applications/{a['id']}/roles", json={"name": "viewer"}).json()
        if not active:
            client.patch(f"/api/admin/applications/{a['id']}", json={"is_active": False})
        return a, role

    hub, hub_viewer = system("Mail Hub", "http://hub.local/")
    plain, plain_viewer = system("Mail Plain", "")
    off, off_viewer = system("Mail Off", "http://off.local/", active=False)
    try:
        assert client.post("/api/admin/users", json={
            "username": "mail.ko", "full_name": "Test mail.ko", "email": "mail.ko@pahtama.com", "password": "first-pass-1",
            "role_ids": [999999]}).status_code == 400  # not a role: nothing created
        created = client.post("/api/admin/users", json={
            "username": "mail.ko", "full_name": "Test mail.ko", "email": "mail.ko@pahtama.com", "password": "first-pass-1",
            "role_ids": [hub_viewer["id"], plain_viewer["id"], off_viewer["id"]]}).json()
        assert sorted(created["role_ids"]) == sorted([hub_viewer["id"], plain_viewer["id"], off_viewer["id"]])
        body = sent[-1]
        assert "You have access to:" in body
        assert "  - Mail Hub (viewer): http://hub.local/" in body
        assert "  - Mail Plain (viewer)\n" in body  # no launch URL: name only
        assert "Mail Off" not in body  # disabled system isn't listed
        actions = [e for e in client.get("/api/admin/audit").json() if e["target"] == "mail.ko"]
        assert {"user.create", "user.roles"} <= {e["action"] for e in actions}
        client.delete(f"/api/admin/users/{created['id']}")
    finally:
        for a in (hub, plain, off):
            client.delete(f"/api/admin/applications/{a['id']}")


def test_no_mail_server_says_so(client: TestClient):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "mail.nomail", "full_name": "Test mail.nomail", "email": "mail.nomail@pahtama.com", "password": "first-pass-1"}).json()
    try:
        assert created["emailed"] is False  # no SMTP_HOST in the tests
    finally:
        client.delete(f"/api/admin/users/{created['id']}")
