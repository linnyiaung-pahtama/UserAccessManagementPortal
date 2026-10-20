"""A user created by an admin is emailed their sign-in details (routers/users.py)."""
from fastapi.testclient import TestClient

import app.routers.users as users


def test_new_user_is_emailed_their_sign_in_details(client: TestClient, monkeypatch):
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(users, "send_mail", lambda to, subject, body: sent.append((to, subject, body)) or True)
    monkeypatch.setattr(users, "mail_configured", lambda: True)

    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "mail.min", "email": "Mail.Min@pahtama.com", "password": "first-pass-1"}).json()
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


def test_no_mail_server_says_so(client: TestClient):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "mail.nomail", "email": "mail.nomail@pahtama.com", "password": "first-pass-1"}).json()
    try:
        assert created["emailed"] is False  # no SMTP_HOST in the tests
    finally:
        client.delete(f"/api/admin/users/{created['id']}")
