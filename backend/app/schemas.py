from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,100}$"
ROLE_PATTERN = r"^[A-Za-z0-9._:-]{1,100}$"
PERMISSION_PATTERN = r"^[A-Za-z0-9._:-]{1,100}$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)  # username or email
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


# ---------------------------------------------------------------- users

class UserOut(ORM):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    must_change_password: bool = False
    created_at: datetime
    last_login_at: datetime | None


class UserDetail(UserOut):
    role_ids: list[int]


class SystemAccess(BaseModel):
    application_id: int
    application_name: str
    roles: list[str]


class UserListItem(UserOut):
    access: list[SystemAccess]


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    is_admin: bool = False
    is_active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    is_admin: bool | None = None
    is_active: bool | None = None


class AssignRolesRequest(BaseModel):
    role_ids: list[int]


# ---------------------------------------------------------------- applications & roles

class RoleOut(ORM):
    id: int
    application_id: int
    name: str
    description: str
    permission_ids: list[int] = []


class PermissionOut(ORM):
    id: int
    application_id: int
    name: str
    description: str


class PermissionCreate(BaseModel):
    name: str = Field(pattern=PERMISSION_PATTERN)
    description: str = ""


class PermissionUpdate(BaseModel):
    name: str | None = Field(default=None, pattern=PERMISSION_PATTERN)
    description: str | None = None


class RolePermissionsRequest(BaseModel):
    """Full role → permission mapping for one application: {role_id: [permission_id, ...]}."""
    roles: dict[int, list[int]]


class RoleCreate(BaseModel):
    name: str = Field(pattern=ROLE_PATTERN)
    description: str = ""


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, pattern=ROLE_PATTERN)
    description: str | None = None


def _validate_uris(uris: list[str]) -> list[str]:
    cleaned = []
    for uri in uris:
        uri = uri.strip()
        if not uri:
            continue
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.fragment:
            raise ValueError(f"Invalid redirect URI: {uri!r} (absolute http(s) URL without #fragment)")
        cleaned.append(uri)
    return cleaned


def _validate_origins(origins: list[str]) -> list[str]:
    """Origins are scheme://host[:port] only, e.g. https://lpc.company.com."""
    cleaned = []
    for origin in origins:
        origin = origin.strip().rstrip("/").lower()
        if not origin:
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query \
                or parsed.fragment:
            raise ValueError(f"Invalid web origin: {origin!r} (use scheme://host[:port], no path)")
        if origin not in cleaned:
            cleaned.append(origin)
    return cleaned


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # No client_id here: the portal generates it from the name (see applications._generate_client_id).
    description: str = ""
    home_url: str = Field(default="", max_length=500)
    redirect_uris: list[str] = []
    web_origins: list[str] = []
    confidential: bool = True  # False for SPAs / mobile apps (PKCE, no secret)

    @field_validator("redirect_uris")
    @classmethod
    def _check_uris(cls, v):
        return _validate_uris(v)

    @field_validator("web_origins")
    @classmethod
    def _check_origins(cls, v):
        return _validate_origins(v)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    home_url: str | None = Field(default=None, max_length=500)
    redirect_uris: list[str] | None = None
    web_origins: list[str] | None = None
    is_active: bool | None = None

    @field_validator("redirect_uris")
    @classmethod
    def _check_uris(cls, v):
        return None if v is None else _validate_uris(v)

    @field_validator("web_origins")
    @classmethod
    def _check_origins(cls, v):
        return None if v is None else _validate_origins(v)


class ApplicationOut(ORM):
    id: int
    name: str
    description: str
    client_id: str
    redirect_uris: list[str]
    web_origins: list[str] = []
    home_url: str
    is_active: bool
    is_confidential: bool

    @field_validator("web_origins", mode="before")
    @classmethod
    def _none_is_empty(cls, v):
        return v or []
    created_at: datetime
    roles: list[RoleOut]
    permissions: list[PermissionOut] = []
    member_count: int = 0


class ApplicationWithSecret(ApplicationOut):
    client_secret: str | None = None  # shown once, never stored in clear text


class Member(BaseModel):
    user_id: int
    username: str
    email: str
    is_active: bool
    roles: list[str]


# ---------------------------------------------------------------- self-service & audit

class MyApplication(BaseModel):
    id: int
    name: str
    description: str
    home_url: str
    roles: list[str]
    permissions: list[str] = []


class SystemSummary(BaseModel):
    id: int
    name: str
    is_active: bool
    role_count: int
    member_count: int


class Overview(BaseModel):
    users_total: int
    users_active: int
    admins: int
    systems_total: int
    sign_ins_24h: int
    failed_sign_ins_24h: int
    sso_grants_24h: int
    denied_24h: int
    systems: list[SystemSummary]


class AuditOut(ORM):
    id: int
    created_at: datetime
    actor_username: str | None
    action: str
    target: str
    detail: str
    ip: str


# ---------------------------------------------------------------- access requests

class RequestableSystem(BaseModel):
    """An active system shown on the public Request access page."""
    id: int
    name: str
    client_id: str  # lets the page pre-select the system the person came from


class AccessRequestCreate(BaseModel):
    email: EmailStr
    application_id: int


class RoleChoice(BaseModel):
    id: int
    name: str


class AccessRequestOut(BaseModel):
    id: int
    email: str
    application_id: int
    application_name: str
    status: str  # open, approved, declined
    created_at: datetime
    handled_at: datetime | None
    handled_by: str | None
    user_id: int | None  # the account with this email, if there is one
    username: str | None
    user_active: bool | None
    current_roles: list[str]  # the account's roles in this system already
    roles: list[RoleChoice]  # the system's roles, to choose from when approving


class AccessRequestApprove(BaseModel):
    role_id: int
    # Only when there is no account with the request's email yet: the new account.
    username: str | None = Field(default=None, pattern=USERNAME_PATTERN)
    password: str | None = Field(default=None, min_length=8, max_length=72)
