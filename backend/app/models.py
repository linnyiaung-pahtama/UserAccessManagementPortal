from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Table, Unicode, UnicodeText, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .security import utcnow

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    # No ON DELETE CASCADE here: SQL Server rejects two cascade paths from applications (via roles and via
    # permissions). SQLAlchemy removes these rows itself when a permission or role is deleted.
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Unicode(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(Unicode(255), unique=True, index=True)
    # No longer used (users are identified by username only); kept so existing databases need no change.
    full_name: Mapped[str] = mapped_column(Unicode(255), default="")
    password_hash: Mapped[str] = mapped_column(Unicode(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # may administer the portal
    # Set when an admin creates the account or resets its password: the user must choose their own
    # password before the portal lets them into the portal or any system.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users")

    def roles_in(self, application_id: int) -> list[str]:
        return sorted(r.name for r in self.roles if r.application_id == application_id)

    def permissions_in(self, application_id: int) -> list[str]:
        """Union of the permissions granted by the user's roles in one application."""
        return sorted({
            p.name for r in self.roles if r.application_id == application_id for p in r.permissions
        })


class Application(Base):
    """A company system that signs users in through the portal (an OIDC client)."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100), unique=True)
    description: Mapped[str] = mapped_column(UnicodeText, default="")
    client_id: Mapped[str] = mapped_column(Unicode(100), unique=True, index=True)
    # NULL = public client (SPA / mobile) that must use PKCE instead of a secret.
    client_secret_hash: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Browser origins (scheme://host:port) allowed to call the portal's OIDC endpoints
    # directly, for single-page apps. Keycloak calls this "Web origins".
    web_origins: Mapped[list[str]] = mapped_column(JSON, default=list)
    home_url: Mapped[str] = mapped_column(Unicode(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    roles: Mapped[list["Role"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="Role.name"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="Permission.name"
    )

    @property
    def is_confidential(self) -> bool:
        return self.client_secret_hash is not None


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("application_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Unicode(100))
    description: Mapped[str] = mapped_column(UnicodeText, default="")

    application: Mapped[Application] = relationship(back_populates="roles")
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")

    @property
    def permission_ids(self) -> list[int]:
        return sorted(p.id for p in self.permissions)


class Permission(Base):
    """Something a user may do inside one application, granted through roles."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("application_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Unicode(100))
    description: Mapped[str] = mapped_column(UnicodeText, default="")

    application: Mapped[Application] = relationship(back_populates="permissions")
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class PortalSession(Base):
    """The SSO session: while it's valid, systems get a sign-in without a password prompt."""

    __tablename__ = "portal_sessions"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)  # sha256 of cookie value
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    code_hash: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    redirect_uri: Mapped[str] = mapped_column(Unicode(500))
    scope: Mapped[str] = mapped_column(Unicode(500))
    nonce: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    code_challenge: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    auth_time: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(Unicode(500))
    auth_time: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AccessRequest(Base):
    """Someone asking, from the sign-in page, for access to a system. Admins approve (create the account if needed
    and give a role) or decline it."""

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Unicode(255), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(Unicode(20), default="open", index=True)  # open, approved, declined
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str] = mapped_column(Unicode(64), default="")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handled_by: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)  # admin's username
    reason: Mapped[str] = mapped_column(Unicode(500), default="")  # why it was declined (optional; emailed)

    application: Mapped[Application] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # No FK: entries must survive user deletion.
    actor_id: Mapped[int | None] = mapped_column(nullable=True)
    actor_username: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    action: Mapped[str] = mapped_column(Unicode(100), index=True)
    target: Mapped[str] = mapped_column(Unicode(255), default="")
    detail: Mapped[str] = mapped_column(UnicodeText, default="")
    ip: Mapped[str] = mapped_column(Unicode(64), default="")
