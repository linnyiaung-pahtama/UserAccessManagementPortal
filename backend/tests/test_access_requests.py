"""Access requests: asked for on the public Request access page, approved or declined by an admin."""
from fastapi.testclient import TestClient

import app.routers.access_requests as access_requests
from app.config import settings
from app.main import app

REDIRECT = "http://req.local/callback"


def test_request_approve_and_decline(client: TestClient, monkeypatch):
    mails: list[tuple[list[str], str]] = []
    bodies: list[str] = []
    monkeypatch.setattr(access_requests, "send_mail",
                        lambda to, subject, body: mails.append((to, subject)) or bodies.append(body) or True)
    access_requests._recent.clear()

    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    system = client.post("/api/admin/applications", json={"name": "Req System", "redirect_uris": [REDIRECT]}).json()
    viewer = client.post(f"/api/admin/applications/{system['id']}/roles", json={"name": "viewer"}).json()
    other = client.post("/api/admin/applications", json={"name": "Req Other", "redirect_uris": [REDIRECT]}).json()
    other_role = client.post(f"/api/admin/applications/{other['id']}/roles", json={"name": "user"}).json()

    with TestClient(app) as public:  # nobody signed in
        systems = public.get("/api/access-requests/systems").json()
        assert {"id": system["id"], "name": "Req System", "client_id": system["client_id"]} in systems

        ask = lambda email, app_id=system["id"]: public.post(  # noqa: E731
            "/api/access-requests", json={"email": email, "application_id": app_id})
        assert ask("someone@gmail.com").status_code == 400  # company addresses only
        assert ask("new.person@pahtama.com", 999999).status_code == 400  # not a system
        assert ask("new.person@pahtama.com").status_code == 202
        assert ask("New.Person@pahtama.com").status_code == 202  # same open request: no duplicate
        assert mails == [([settings.admin_email], "Access request: new.person@pahtama.com for Req System")]

        # The public side cannot see or handle requests.
        assert public.get("/api/admin/access-requests").status_code == 401

    open_ = client.get("/api/admin/access-requests?status=open").json()
    mine = [r for r in open_ if r["email"] == "new.person@pahtama.com"]
    assert len(mine) == 1 and mine[0]["user_id"] is None and mine[0]["roles"] == [{"id": viewer["id"], "name": "viewer"}]
    assert client.get("/api/admin/access-requests/count").json()["open"] >= 1
    rid = mine[0]["id"]

    # Approving a request with no account needs a username and password, and one of this system's roles.
    assert client.post(f"/api/admin/access-requests/{rid}/approve", json={"role_id": viewer["id"]}).status_code == 400
    bad_role = {"role_id": other_role["id"], "username": "new.person", "full_name": "New Person", "password": "temp-pass-1"}
    assert client.post(f"/api/admin/access-requests/{rid}/approve", json=bad_role).status_code == 400
    approved = client.post(f"/api/admin/access-requests/{rid}/approve",
                           json={"role_id": viewer["id"], "username": "new.person", "full_name": "New Person", "password": "temp-pass-1"}).json()
    assert approved["status"] == "approved" and approved["handled_by"] == "admin"
    assert approved["username"] == "new.person" and approved["current_roles"] == ["viewer"]
    user = client.get(f"/api/admin/users/{approved['user_id']}").json()
    assert user["must_change_password"] is True and user["role_ids"] == [viewer["id"]]
    # The requester is emailed their username and temporary password, with where to sign in.
    assert mails[-1] == (["new.person@pahtama.com"], "Your access to Req System is approved")
    assert "Username: new.person" in bodies[-1] and "Temporary password: temp-pass-1" in bodies[-1]
    assert client.post(f"/api/admin/access-requests/{rid}/decline").status_code == 409  # already handled

    with TestClient(app) as public:
        # Already has access to Req System: accepted, but nothing for an admin to do.
        mails.clear()
        assert public.post("/api/access-requests", json={"email": "new.person@pahtama.com", "application_id": system["id"]}).status_code == 202
        assert mails == []
        # An existing account asking for another system: the admin only adds the role.
        assert public.post("/api/access-requests", json={"email": "new.person@pahtama.com", "application_id": other["id"]}).status_code == 202
    second = next(r for r in client.get("/api/admin/access-requests?status=open").json() if r["email"] == "new.person@pahtama.com")
    assert second["application_name"] == "Req Other" and second["username"] == "new.person"
    done = client.post(f"/api/admin/access-requests/{second['id']}/approve", json={"role_id": other_role["id"]}).json()
    assert mails[-1] == (["new.person@pahtama.com"], "Your access to Req Other is approved")
    assert "existing account (new.person)" in bodies[-1] and "password" not in bodies[-1].lower()
    assert sorted(done["current_roles"]) == ["user"]
    assert len(client.get(f"/api/admin/users/{done['user_id']}").json()["role_ids"]) == 2

    # Decline.
    with TestClient(app) as public:
        public.post("/api/access-requests", json={"email": "spam.person@pahtama.com", "application_id": system["id"]})
    spam = next(r for r in client.get("/api/admin/access-requests?status=open").json() if r["email"] == "spam.person@pahtama.com")
    declined = client.post(f"/api/admin/access-requests/{spam['id']}/decline", json={"reason": "  Not a staff member.  "}).json()
    assert declined["status"] == "declined" and declined["user_id"] is None and declined["reason"] == "Not a staff member."
    assert mails[-1] == (["spam.person@pahtama.com"], "Your request for access to Req System")
    assert "declined" in bodies[-1] and "Reason: Not a staff member." in bodies[-1]

    actions = [e["action"] for e in client.get("/api/admin/audit").json()]
    assert {"access.request", "access.approve", "access.decline"} <= set(actions)

    # Leave the shared test database as it was.
    client.delete(f"/api/admin/users/{approved['user_id']}")
    for a in (system, other):
        client.delete(f"/api/admin/applications/{a['id']}")


def test_requests_are_rate_limited(client: TestClient, monkeypatch):
    monkeypatch.setattr(access_requests, "send_mail", lambda *a: True)
    access_requests._recent.clear()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-pass"}).status_code == 200
    system = client.post("/api/admin/applications", json={"name": "Req Limit", "redirect_uris": [REDIRECT]}).json()
    with TestClient(app) as public:
        codes = [public.post("/api/access-requests", json={"email": f"limit{i}@pahtama.com", "application_id": system["id"]}).status_code
                 for i in range(access_requests.LIMIT_PER_HOUR + 1)]
    assert codes[:-1] == [202] * access_requests.LIMIT_PER_HOUR and codes[-1] == 429
    access_requests._recent.clear()
    client.delete(f"/api/admin/applications/{system['id']}")


def test_mail_is_off_without_a_mail_server():
    from app.mailer import send_mail
    assert send_mail(["admin@pahtama.com"], "x", "y") is False  # no SMTP_HOST in the tests
