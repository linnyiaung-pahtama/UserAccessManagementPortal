"""Create sample users through the running portal's admin API (so it's audited).

    python -m app.seed_users

Requires the backend to be running and the systems to be registered (python -m app.seed_demo).
Re-running adds any missing sample roles to existing users.

Creates the Promotion Approval Form's users: a requester per business unit, and one approver
account per approver profile its DOA rules route to. PAF recognises approvers by email, so each account's
email (username@example.com) matches its profile in PromotionApprovalForm/backend/data/approvers.csv.
All sample users share one password, SEED_USER_PASSWORD in backend/.env
(generated and saved there on first run).
"""

import os
import sys
from pathlib import Path

import httpx

from .config import settings
from .security import new_token

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# username, display name (for reference only; the portal uses the username), {client_id: roles}, active
SAMPLE_USERS = [
    ("alice.tan", "Alice Tan", {"promotion-approval": ["requester"]}, True),
    ("bob.lim", "Bob Lim", {"promotion-approval": ["approver"]}, True),   # role but no approver profile (test)
    ("chloe.ng", "Chloe Ng", {}, True),                                    # no system access (test)
    ("david.wong", "David Wong", {}, True),
    ("emma.lee", "Emma Lee", {}, True),
    ("frank.ho", "Frank Ho", {}, False),                                   # disabled (test)
    # Promotion Approval Form requesters (Trade Marketing), one per business unit
    ("nandar.hlaing", "Nandar Hlaing", {"promotion-approval": ["requester"]}, True),   # PG
    ("thura.aung", "Thura Aung", {"promotion-approval": ["requester"]}, True),         # PDG
]

# Promotion Approval Form approvers: one account per approver profile its DOA rules route to
# (PAF's data/approvers.csv + promotional_approvers.csv). Names are PAF's sample data, not real accounts yet.
PAF_APPROVERS = [
    ("hlaing.min", "Hlaing Min"),                # PAF approver 1: Managing Director
    ("zaw.min.latt", "Zaw Min Latt"),              # PAF approver 2: Approver Two, Management, BU Head
    ("ronald.lee", "Ronald Lee"),                # PAF approver 3: Finance
    ("theingi.aung", "Theingi Aung"),              # PAF approver 13: Approver One
    ("myat.nyein.su", "Myat Nyein Su"),             # PAF approver 60: Approver Two
    ("phyo.wai.maung", "Phyo Wai Maung"),            # PAF approver 61: Approver One
    ("linn.linn.khine", "Linn Linn Khine"),           # PAF approver 62: Approver One, Approver Two
    ("cho.nwe.myint", "Cho Nwe Myint"),             # PAF approver 65: Approver One
    ("aye.myint.oo", "Aye Myint Oo"),              # PAF approver 68: Approver One
    ("zaw.zaw.naing", "Zaw Zaw Naing"),             # PAF approver 69: Approver One
    ("kong.mun.keen", "Kong Mun Keen"),             # PAF approver 71: Approver Two
    ("aung.naing.win", "Aung Naing Win"),            # PAF approver 73: Approver One
    ("aung.khant.kyaw", "Aung Khant Kyaw"),           # PAF approver 79: Approver One, Approver Two
    ("phyo.min.ko", "Phyo Min Ko"),               # PAF approver 80: Approver One
    ("mo.mo.phone.maw", "Mo Mo Phone Maw"),           # PAF approver 81: Approver One, Approver Two
    ("win.thida", "Win Thida"),                 # PAF approver 83: Approver One
    ("yu.wah.oo", "Yu Wah Oo"),                 # PAF approver 85: Approver One
    ("han.yin.aye", "Han Yin Aye"),               # PAF approver 88: Approver One
    ("tin.tun.aung", "Tin Tun Aung"),              # PAF approver 95: Approver One
    ("thet.htar.swe", "Thet Htar Swe"),             # PAF approver 103: Approver One, Approver Two
    ("su.sandy.linn", "Su Sandy Linn"),             # PAF approver 110: Accounts Check
    ("yan.naing", "Yan Naing"),                 # PAF approver 115: Approver One
    ("khin.moe.moe.aung", "Khin Moe Moe Aung"),         # PAF approver 116: Approver One
    ("hnin.wutt.yi", "Hnin Wutt Yi"),              # PAF approver 117: Accounts Check
    ("khaing.zar.lin", "Khaing Zar Lin"),            # PAF approver 118: Accounts Check
    ("hnin.nwe.nwe.win", "Hnin Nwe Nwe Win"),          # PAF approver 119: Accounts Check
    ("ei.cho.the", "Ei Cho The"),                # PAF approver 126: Approver One
    ("myo.min.htet", "Myo Min Htet"),              # PAF approver 129: Approver One
    ("win.pa.pa.tun", "Win Pa Pa Tun"),             # PAF approver 130: Approver One
    ("ei.ei.phyu", "Ei Ei Phyu"),                # PAF approver 131: Approver One
    ("hnin.yee.thein", "Hnin Yee Thein"),            # PAF approver 132: Approver One
    ("kyaw.min.aung", "Kyaw Min Aung"),             # PAF approver 133: Approver One
    ("thae.ma.ma.soe", "Thae Ma Ma Soe"),            # PAF approver 134: Approver One
    ("wine.eaindra.kyaing", "Wine Eaindra Kyaing"),       # PAF approver 136: Approver One
    ("thinzar.tun", "Thinzar Tun"),               # PAF approver 140: Approver One
]
SAMPLE_USERS += [(username, name, {"promotion-approval": ["approver"]}, True) for username, name in PAF_APPROVERS]


def seed_password() -> str:
    password = os.getenv("SEED_USER_PASSWORD")
    if password:
        return password
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines() if ENV_FILE.exists() else []:
        if line.startswith("SEED_USER_PASSWORD=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    password = new_token(12)
    with ENV_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n# Shared password for sample users created by app.seed_users\nSEED_USER_PASSWORD={password}\n")
    return password


def main() -> None:
    if not settings.admin_password:
        sys.exit("ADMIN_PASSWORD must be set in backend/.env to sign in as admin.")
    password = seed_password()

    with httpx.Client(base_url=settings.issuer, timeout=10) as api:
        r = api.post("/api/auth/login", json={"username": settings.admin_username, "password": settings.admin_password})
        r.raise_for_status()

        apps = {a["client_id"]: a for a in api.get("/api/admin/applications").json()}
        needed = {cid for _, _, access, _ in SAMPLE_USERS for cid in access}
        missing = needed - apps.keys()
        if missing:
            sys.exit(f"Not registered: {', '.join(sorted(missing))}. Run: python -m app.seed_demo")
        role_ids = {(cid, r["name"]): r["id"] for cid, a in apps.items() for r in a["roles"]}

        existing = {u["username"]: u for u in api.get("/api/admin/users").json()}
        for username, display_name, access, active in SAMPLE_USERS:
            if username in existing:
                user = api.get(f"/api/admin/users/{existing[username]['id']}").json()
                verb = "update"
            else:
                r = api.post("/api/admin/users", json={
                    "username": username,
                    "full_name": display_name,
                    "email": f"{username}@example.com",
                    "password": password,
                    "is_active": active,
                })
                r.raise_for_status()
                user = r.json()
                verb = "added"

            wanted = {role_ids[(cid, name)] for cid, names in access.items() for name in names}
            if not wanted <= set(user["role_ids"]):
                api.put(f"/api/admin/users/{user['id']}/roles",
                        json={"role_ids": sorted(wanted | set(user["role_ids"]))}).raise_for_status()
            elif verb == "update":
                verb = "ok"

            summary = "; ".join(f"{apps[cid]['name']}: {', '.join(names)}" for cid, names in access.items())
            status = "" if active else " [disabled]"
            print(f"  {verb:<6} {username:<11} {summary}{status}")

    print(f"Done. Sample users' password is SEED_USER_PASSWORD in {ENV_FILE}")


if __name__ == "__main__":
    main()
