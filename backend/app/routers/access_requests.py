"""Access requests: someone without access asks for it on the public Request access page (linked under the sign-in
form), and an admin approves (creating the account if needed and giving a role in the system) or declines it.

The public side never says whether an account exists: every accepted request gets the same answer."""

import time
from collections import defaultdict, deque

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..database import get_db
from ..deps import audit, require_admin
from ..mailer import send_mail
from ..models import AccessRequest, Application, Role, User
from ..schemas import (
    AccessRequestApprove,
    AccessRequestCreate,
    AccessRequestOut,
    RequestableSystem,
    RoleChoice,
)
from ..security import hash_password, utcnow
from .users import _check_domain, _ensure_unique

public = APIRouter(prefix="/api/access-requests", tags=["access requests"])
router = APIRouter(prefix="/api/admin/access-requests", tags=["admin: access requests"])

STATUSES = ("open", "approved", "declined")

# At most this many requests per hour from one address (the page is public). In memory: a restart resets it.
LIMIT_PER_HOUR = 5
_recent: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    hits = _recent[ip]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= LIMIT_PER_HOUR:
        return True
    hits.append(now)
    return False


# ---------------------------------------------------------------- public

@public.get("/systems", response_model=list[RequestableSystem])
def requestable_systems(db: DbSession = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.is_active == true()).order_by(Application.name)).all()
    return [RequestableSystem(id=a.id, name=a.name, client_id=a.client_id) for a in apps]


@public.post("", status_code=202)
def create_request(body: AccessRequestCreate, request: Request, background: BackgroundTasks,
                   db: DbSession = Depends(get_db)):
    email = str(body.email).lower()
    _check_domain(email)
    app = db.get(Application, body.application_id)
    if not app or not app.is_active:
        raise HTTPException(400, "Choose a system from the list")
    ip = request.client.host if request.client else ""
    if _rate_limited(ip):
        raise HTTPException(429, "Too many requests. Please try again later.")

    received = {"status": "received"}
    user = db.scalar(select(User).where(User.email == email))
    if user and user.is_active and user.roles_in(app.id):
        return received  # already has access: nothing for an admin to do
    already_open = db.scalar(select(AccessRequest).where(
        AccessRequest.email == email, AccessRequest.application_id == app.id, AccessRequest.status == "open"))
    if already_open:
        return received

    db.add(AccessRequest(email=email, application_id=app.id, ip=ip))
    audit(db, None, "access.request", target=email, detail=app.name, request=request)
    db.commit()

    admins = db.scalars(select(User.email).where(User.is_admin == true(), User.is_active == true())).all()
    background.add_task(
        send_mail, sorted(admins), f"Access request: {email} for {app.name}",
        f"{email} asked for access to {app.name}.\n\n"
        f"Review it in the Access Portal: {settings.frontend_url}/admin/access-requests\n",
    )
    return received


# ---------------------------------------------------------------- admin

def _out(db: DbSession, r: AccessRequest) -> AccessRequestOut:
    user = db.scalar(select(User).where(User.email == r.email))
    return AccessRequestOut(
        id=r.id, email=r.email, application_id=r.application_id, application_name=r.application.name,
        status=r.status, created_at=r.created_at, handled_at=r.handled_at, handled_by=r.handled_by,
        user_id=user.id if user else None, username=user.username if user else None,
        user_active=user.is_active if user else None,
        current_roles=user.roles_in(r.application_id) if user else [],
        roles=[RoleChoice(id=role.id, name=role.name) for role in r.application.roles],
    )


def _get_open(db: DbSession, request_id: int) -> AccessRequest:
    r = db.get(AccessRequest, request_id)
    if not r:
        raise HTTPException(404, "Request not found")
    if r.status != "open":
        raise HTTPException(409, f"This request was already {r.status}")
    return r


@router.get("", response_model=list[AccessRequestOut])
def list_requests(status: str | None = None, db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(AccessRequest).order_by(AccessRequest.created_at.desc(), AccessRequest.id.desc())
    if status in STATUSES:
        stmt = stmt.where(AccessRequest.status == status)
    return [_out(db, r) for r in db.scalars(stmt.limit(500)).all()]


@router.get("/count")
def open_count(db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    return {"open": db.scalar(select(func.count(AccessRequest.id)).where(AccessRequest.status == "open"))}


@router.post("/{request_id}/approve", response_model=AccessRequestOut)
def approve(request_id: int, body: AccessRequestApprove, request: Request, db: DbSession = Depends(get_db),
            admin: User = Depends(require_admin)):
    r = _get_open(db, request_id)
    role = db.get(Role, body.role_id)
    if not role or role.application_id != r.application_id:
        raise HTTPException(400, f"Choose one of {r.application.name}'s roles")

    user = db.scalar(select(User).where(User.email == r.email))
    if not user:
        if not body.username or not body.password:
            raise HTTPException(400, "There is no account with this email yet: enter a username and a temporary password")
        _check_domain(r.email)
        _ensure_unique(db, username=body.username)
        user = User(username=body.username, email=r.email, password_hash=hash_password(body.password),
                    must_change_password=True)  # temporary, like any admin-set password
        db.add(user)
        audit(db, admin, "user.create", target=user.username, detail="from an access request", request=request)
    if role not in user.roles:
        user.roles.append(role)
        audit(db, admin, "user.roles", target=user.username, detail=f"added: {r.application.name}:{role.name}",
              request=request)

    r.status, r.handled_at, r.handled_by = "approved", utcnow(), admin.username
    audit(db, admin, "access.approve", target=r.email, detail=f"{r.application.name}:{role.name}", request=request)
    db.commit()
    return _out(db, r)


@router.post("/{request_id}/decline", response_model=AccessRequestOut)
def decline(request_id: int, request: Request, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    r = _get_open(db, request_id)
    r.status, r.handled_at, r.handled_by = "declined", utcnow(), admin.username
    audit(db, admin, "access.decline", target=r.email, detail=r.application.name, request=request)
    db.commit()
    return _out(db, r)
