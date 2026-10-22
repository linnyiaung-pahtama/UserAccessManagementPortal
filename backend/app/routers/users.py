from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession, selectinload

from ..config import settings
from ..database import get_db
from ..deps import audit, require_admin, terminate_user_sessions
from ..mailer import mail_configured, send_mail
from ..models import Role, User
from ..schemas import (
    AssignRolesRequest,
    SystemAccess,
    UserCreate,
    UserDetail,
    UserListItem,
    UserOut,
    UserUpdate,
)
from ..security import hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin: users"])


def _get_user(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _detail(user: User) -> UserDetail:
    return UserDetail(
        **UserOut.model_validate(user).model_dump(), role_ids=sorted(r.id for r in user.roles)
    )


def _ensure_unique(db: DbSession, *, username: str | None = None, email: str | None = None,
                   exclude_id: int | None = None) -> None:
    if username:
        # Capitals don't make a different username ("Mya" = "mya"), as SQL Server already treats them.
        existing = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if existing and existing.id != exclude_id:
            raise HTTPException(409, "Username is already taken")
    if email:
        existing = db.scalar(select(User).where(User.email == email))
        if existing and existing.id != exclude_id:
            raise HTTPException(409, "Email is already in use")


def _check_domain(email: str) -> None:
    domain = settings.allowed_email_domain.lower()
    if email.rsplit("@", 1)[-1] != domain:
        raise HTTPException(400, f"Email must be a company address (@{domain})")


def _role_label(role: Role) -> str:
    return f"{role.application.name}:{role.name}"


def _access(user: User) -> list[SystemAccess]:
    by_app: dict[int, SystemAccess] = {}
    for role in user.roles:
        entry = by_app.setdefault(
            role.application_id,
            SystemAccess(application_id=role.application_id, application_name=role.application.name, roles=[]),
        )
        entry.roles.append(role.name)
    for entry in by_app.values():
        entry.roles.sort()
    return sorted(by_app.values(), key=lambda a: a.application_name)


@router.get("", response_model=list[UserListItem])
def list_users(q: str | None = None, db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.application))
        .order_by(User.username)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.full_name.ilike(like), User.email.ilike(like)))
    return [
        UserListItem(**UserOut.model_validate(u).model_dump(), access=_access(u))
        for u in db.scalars(stmt).all()
    ]


@router.post("", response_model=UserDetail, status_code=201)
def create_user(body: UserCreate, request: Request, background: BackgroundTasks, db: DbSession = Depends(get_db),
                admin: User = Depends(require_admin)):
    email = str(body.email).lower()
    _check_domain(email)
    _ensure_unique(db, username=body.username, email=email)
    wanted = set(body.role_ids)
    roles = db.scalars(select(Role).where(Role.id.in_(wanted))).all() if wanted else []
    if len(roles) != len(wanted):
        raise HTTPException(400, "One or more role ids do not exist")
    user = User(
        username=body.username,
        full_name=body.full_name,
        email=email,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        is_active=body.is_active,
        must_change_password=True,  # the admin chose this password; the user replaces it on first sign-in
        roles=list(roles),
    )
    db.add(user)
    audit(db, admin, "user.create", target=body.username, request=request)
    if roles:
        audit(db, admin, "user.roles", target=body.username,
              detail=f"added: {', '.join(sorted(_role_label(r) for r in roles))}", request=request)
    db.commit()
    # Their sign-in details, by email (when a mail server is set). The password is temporary: the portal makes them
    # choose their own at the first sign-in.
    background.add_task(send_mail, [email], "Your Access Portal account", _welcome_email(user, body.password))
    return _detail(user).model_copy(update={"emailed": mail_configured()})


def _welcome_email(user: User, password: str) -> str:
    """The new account's sign-in details, and the systems they were given (with each one's address)."""
    lines = [
        f"Hello {user.display_name},", "", "An account was created for you in the company Access Portal.", "",
        f"  Username: {user.username}", f"  Email: {user.email}", f"  Temporary password: {password}", "",
        f"Sign in here: {settings.frontend_url}/login", "",
        "You will be asked to choose your own password the first time you sign in.",
    ]
    apps = {r.application_id: r.application for r in user.roles}
    # Nobody can sign in to a disabled system, so it isn't listed.
    granted = [(apps[a.application_id], a.roles) for a in _access(user) if apps[a.application_id].is_active]
    if granted:
        lines += ["", "You have access to:"]
        for app, roles in granted:
            where = f": {app.home_url}" if app.home_url else ""
            lines.append(f"  - {app.name} ({', '.join(roles)}){where}")
    return "\n".join(lines) + "\n"


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: int, db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    return _detail(_get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(user_id: int, body: UserUpdate, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if user.id == admin.id and (data.get("is_active") is False or data.get("is_admin") is False):
        raise HTTPException(400, "You cannot deactivate or remove admin rights from your own account")

    kill_sessions = False
    old_username = user.username
    if "username" in data and data["username"] != user.username:
        # Sign-in uses the new name from now on. (PAF links people by email, Project Hub by user id: unaffected.)
        _ensure_unique(db, username=data["username"], exclude_id=user.id)
        user.username = data["username"]
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "email" in data:
        email = str(data["email"]).lower()
        if email != user.email:  # only new addresses are checked, so older accounts can still be edited
            _check_domain(email)
        _ensure_unique(db, email=email, exclude_id=user.id)
        user.email = email
    if "is_admin" in data:
        user.is_admin = data["is_admin"]
    if "is_active" in data:
        user.is_active = data["is_active"]
        kill_sessions |= not data["is_active"]
    if "password" in data:
        user.password_hash = hash_password(data["password"])
        user.must_change_password = user.id != admin.id  # a reset password is temporary, like a new one
        kill_sessions = True
    if kill_sessions:
        terminate_user_sessions(db, user.id)

    changed = ", ".join(sorted(data))
    if user.username != old_username:
        changed += f" (username was {old_username})"
    audit(db, admin, "user.update", target=user.username, detail=changed, request=request)
    db.commit()
    return _detail(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    audit(db, admin, "user.delete", target=user.username, request=request)
    db.delete(user)
    db.commit()


@router.put("/{user_id}/roles", response_model=UserDetail)
def set_user_roles(user_id: int, body: AssignRolesRequest, request: Request,
                   db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Replace the user's full set of roles across all systems."""
    user = _get_user(db, user_id)
    wanted = set(body.role_ids)
    roles = db.scalars(select(Role).where(Role.id.in_(wanted))).all() if wanted else []
    if len(roles) != len(wanted):
        raise HTTPException(400, "One or more role ids do not exist")

    before = {_role_label(r) for r in user.roles}
    after = {_role_label(r) for r in roles}
    user.roles = list(roles)
    added, removed = sorted(after - before), sorted(before - after)
    if added or removed:
        detail = "; ".join(
            part for part in (
                f"added: {', '.join(added)}" if added else "",
                f"removed: {', '.join(removed)}" if removed else "",
            ) if part
        )
        audit(db, admin, "user.roles", target=user.username, detail=detail, request=request)
    db.commit()
    return _detail(user)
