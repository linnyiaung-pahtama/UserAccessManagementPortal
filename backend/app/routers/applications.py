import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session as DbSession

from ..cors import invalidate_origins_cache
from ..database import get_db
from ..deps import audit, require_admin
from ..models import Application, Permission, Role, User, user_roles
from ..schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    ApplicationWithSecret,
    Member,
    PermissionCreate,
    PermissionOut,
    PermissionUpdate,
    RoleCreate,
    RoleOut,
    RolePermissionsRequest,
    RoleUpdate,
)
from ..security import hash_token, new_token

router = APIRouter(prefix="/api/admin/applications", tags=["admin: applications"])


def _generate_client_id(db: DbSession, name: str) -> str:
    """The system's client ID, made from its name: lower-case letters and digits joined by dashes
    ("Promotion Approval Form" -> "promotion-approval-form"), with -2, -3 ... added if it's taken.
    Admins don't type it, so it's always a valid, unique identifier. It never changes afterwards."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:90] or "system"
    if len(base) < 2:
        base = f"{base}-system"
    taken = {c.lower() for c in db.scalars(select(Application.client_id))}
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def _get_app(db: DbSession, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return app


def _get_role(db: DbSession, app: Application, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if not role or role.application_id != app.id:
        raise HTTPException(404, "Role not found")
    return role


def _get_permission(db: DbSession, app: Application, permission_id: int) -> Permission:
    permission = db.get(Permission, permission_id)
    if not permission or permission.application_id != app.id:
        raise HTTPException(404, "Permission not found")
    return permission


def member_counts(db: DbSession, app_id: int | None = None) -> dict[int, int]:
    """Number of distinct users holding at least one role, per application."""
    stmt = (
        select(Role.application_id, func.count(distinct(user_roles.c.user_id)))
        .join(user_roles, user_roles.c.role_id == Role.id)
        .group_by(Role.application_id)
    )
    if app_id is not None:
        stmt = stmt.where(Role.application_id == app_id)
    return dict(db.execute(stmt).all())


def _out(db: DbSession, app: Application) -> ApplicationOut:
    out = ApplicationOut.model_validate(app)
    out.member_count = member_counts(db, app.id).get(app.id, 0)
    return out


def _ensure_unique_name(db: DbSession, name: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Application).where(Application.name == name))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "An application with this name already exists")


def _ensure_unique_role(db: DbSession, app: Application, name: str, exclude_id: int | None = None) -> None:
    if any(r.name.lower() == name.lower() and r.id != exclude_id for r in app.roles):  # "Admin" = "admin"
        raise HTTPException(409, f"Role '{name}' already exists in {app.name}")


@router.get("", response_model=list[ApplicationOut])
def list_applications(db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    apps = db.scalars(select(Application).order_by(Application.name)).all()
    counts = member_counts(db)
    return [
        ApplicationOut.model_validate(a).model_copy(update={"member_count": counts.get(a.id, 0)})
        for a in apps
    ]


@router.post("", response_model=ApplicationWithSecret, status_code=201)
def create_application(body: ApplicationCreate, request: Request, db: DbSession = Depends(get_db),
                       admin: User = Depends(require_admin)):
    name = body.name.strip()
    _ensure_unique_name(db, name)
    client_id = _generate_client_id(db, name)

    secret = new_token() if body.confidential else None
    app = Application(
        name=name,
        client_id=client_id,
        description=body.description.strip(),
        home_url=body.home_url.strip(),
        redirect_uris=body.redirect_uris,
        web_origins=body.web_origins,
        client_secret_hash=hash_token(secret) if secret else None,
    )
    db.add(app)
    audit(db, admin, "app.create", target=name, detail=f"client_id={client_id}", request=request)
    db.commit()
    invalidate_origins_cache()
    return ApplicationWithSecret(**_out(db, app).model_dump(), client_secret=secret)


@router.get("/{app_id}", response_model=ApplicationOut)
def get_application(app_id: int, db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    return _out(db, _get_app(db, app_id))


@router.patch("/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, request: Request,
                       db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data:
        data["name"] = data["name"].strip()
        _ensure_unique_name(db, data["name"], exclude_id=app.id)
    for field, value in data.items():
        setattr(app, field, value)
    audit(db, admin, "app.update", target=app.name, detail=", ".join(sorted(data)), request=request)
    db.commit()
    invalidate_origins_cache()
    return _out(db, app)


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, request: Request, db: DbSession = Depends(get_db),
                       admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    audit(db, admin, "app.delete", target=app.name, request=request)
    db.delete(app)
    db.commit()
    invalidate_origins_cache()


@router.post("/{app_id}/rotate-secret", response_model=ApplicationWithSecret)
def rotate_secret(app_id: int, request: Request, db: DbSession = Depends(get_db),
                  admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    if not app.is_confidential:
        raise HTTPException(400, "Public clients do not have a client secret")
    secret = new_token()
    app.client_secret_hash = hash_token(secret)
    audit(db, admin, "app.rotate_secret", target=app.name, request=request)
    db.commit()
    return ApplicationWithSecret(**_out(db, app).model_dump(), client_secret=secret)


# ---------------------------------------------------------------- roles

@router.post("/{app_id}/roles", response_model=RoleOut, status_code=201)
def create_role(app_id: int, body: RoleCreate, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    _ensure_unique_role(db, app, body.name)
    role = Role(application=app, name=body.name, description=body.description.strip())
    db.add(role)
    audit(db, admin, "role.create", target=f"{app.name}:{body.name}", request=request)
    db.commit()
    return RoleOut.model_validate(role)


@router.patch("/{app_id}/roles/{role_id}", response_model=RoleOut)
def update_role(app_id: int, role_id: int, body: RoleUpdate, request: Request,
                db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    role = _get_role(db, app, role_id)
    old_label = f"{app.name}:{role.name}"
    if body.name is not None and body.name != role.name:  # a rename: new names are lowercase
        name = body.name.lower()
        _ensure_unique_role(db, app, name, exclude_id=role.id)
        role.name = name
    if body.description is not None:
        role.description = body.description.strip()
    audit(db, admin, "role.update", target=old_label, detail=f"now {app.name}:{role.name}", request=request)
    db.commit()
    return RoleOut.model_validate(role)


@router.delete("/{app_id}/roles/{role_id}", status_code=204)
def delete_role(app_id: int, role_id: int, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    role = _get_role(db, app, role_id)
    if role.users:  # in use: take it away from people first, so nobody loses access by accident
        n = len(role.users)
        raise HTTPException(409, f'{n} user{"" if n == 1 else "s"} still {"has" if n == 1 else "have"} the role '
                                 f'"{role.name}". Remove it from them first, then delete it.')
    audit(db, admin, "role.delete", target=f"{app.name}:{role.name}", request=request)
    db.delete(role)
    db.commit()


@router.get("/{app_id}/members", response_model=list[Member])
def list_members(app_id: int, db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    """Everyone who can sign in to this system, with their roles in it."""
    app = _get_app(db, app_id)
    rows = db.execute(
        select(User, Role)
        .join(User.roles)
        .where(Role.application_id == app.id)
        .order_by(User.username, Role.name)
    ).all()
    members: dict[int, Member] = {}
    for user, role in rows:
        member = members.setdefault(
            user.id,
            Member(user_id=user.id, username=user.username, full_name=user.full_name,
                   email=user.email, is_active=user.is_active, roles=[]),
        )
        member.roles.append(role.name)
    return list(members.values())


# ---------------------------------------------------------------- permissions

def _ensure_unique_permission(app: Application, name: str, exclude_id: int | None = None) -> None:
    if any(p.name.lower() == name.lower() and p.id != exclude_id for p in app.permissions):
        raise HTTPException(409, f"Permission '{name}' already exists in {app.name}")


@router.post("/{app_id}/permissions", response_model=PermissionOut, status_code=201)
def create_permission(app_id: int, body: PermissionCreate, request: Request, db: DbSession = Depends(get_db),
                      admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    _ensure_unique_permission(app, body.name)
    permission = Permission(application=app, name=body.name, description=body.description.strip())
    db.add(permission)
    audit(db, admin, "permission.create", target=f"{app.name}:{body.name}", request=request)
    db.commit()
    return PermissionOut.model_validate(permission)


@router.patch("/{app_id}/permissions/{permission_id}", response_model=PermissionOut)
def update_permission(app_id: int, permission_id: int, body: PermissionUpdate, request: Request,
                      db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    permission = _get_permission(db, app, permission_id)
    old_label = f"{app.name}:{permission.name}"
    if body.name is not None and body.name != permission.name:  # a rename: new names are lowercase
        name = body.name.lower()
        _ensure_unique_permission(app, name, exclude_id=permission.id)
        permission.name = name
    if body.description is not None:
        permission.description = body.description.strip()
    audit(db, admin, "permission.update", target=old_label, detail=f"now {app.name}:{permission.name}",
          request=request)
    db.commit()
    return PermissionOut.model_validate(permission)


@router.delete("/{app_id}/permissions/{permission_id}", status_code=204)
def delete_permission(app_id: int, permission_id: int, request: Request, db: DbSession = Depends(get_db),
                      admin: User = Depends(require_admin)):
    app = _get_app(db, app_id)
    permission = _get_permission(db, app, permission_id)
    # In use = someone holds it through a role. Roles that grant it to nobody don't block it (it's removed from them).
    in_use = sorted(r.name for r in permission.roles if r.users)
    if in_use:
        names = ", ".join(f'"{n}"' for n in in_use)
        raise HTTPException(409, f'"{permission.name}" is in use: users with the role{"" if len(in_use) == 1 else "s"} '
                                 f"{names} have it. Untick it for those roles (or remove those users from them) "
                                 "first, then delete it.")
    roles = ", ".join(r.name for r in permission.roles) or "no roles"
    audit(db, admin, "permission.delete", target=f"{app.name}:{permission.name}",
          detail=f"was granted to {roles}", request=request)
    db.delete(permission)
    db.commit()


@router.put("/{app_id}/role-permissions", response_model=ApplicationOut)
def set_role_permissions(app_id: int, body: RolePermissionsRequest, request: Request,
                         db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Replace which permissions each listed role grants. Roles not listed are left unchanged."""
    app = _get_app(db, app_id)
    roles = {r.id: r for r in app.roles}
    perms = {p.id: p for p in app.permissions}
    for role_id, permission_ids in body.roles.items():
        if role_id not in roles:
            raise HTTPException(400, f"Role {role_id} does not belong to {app.name}")
        unknown = set(permission_ids) - perms.keys()
        if unknown:
            raise HTTPException(400, f"Permission id(s) {sorted(unknown)} do not belong to {app.name}")

    changes = []
    for role_id, permission_ids in body.roles.items():
        role = roles[role_id]
        before = {p.name for p in role.permissions}
        role.permissions = [perms[i] for i in sorted(set(permission_ids))]
        after = {p.name for p in role.permissions}
        added, removed = sorted(after - before), sorted(before - after)
        if added:
            changes.append(f"{role.name} +{', +'.join(added)}")
        if removed:
            changes.append(f"{role.name} -{', -'.join(removed)}")
    if changes:
        audit(db, admin, "role.permissions", target=app.name, detail="; ".join(changes), request=request)
    db.commit()
    return _out(db, app)
