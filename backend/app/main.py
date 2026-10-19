import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select, true

from .config import settings
from .cors import WebOriginsCORS
from .database import SessionLocal, create_schema
from .models import AuthorizationCode, PortalSession, RefreshToken, User
from .routers import access_requests, applications, audit, auth, oauth, overview, users
from .security import hash_password, new_token, signing_keys, utcnow

log = logging.getLogger("uam")


def _bootstrap() -> None:
    create_schema()
    signing_keys.load(settings.keys_dir)
    with SessionLocal() as db:
        now = utcnow()
        db.execute(delete(PortalSession).where(PortalSession.expires_at < now))
        db.execute(delete(AuthorizationCode).where(AuthorizationCode.expires_at < now))
        db.execute(delete(RefreshToken).where(or_(RefreshToken.expires_at < now, RefreshToken.revoked == true())))

        if db.scalar(select(func.count(User.id))) == 0:
            password = settings.admin_password or new_token(12)
            db.add(User(username=settings.admin_username, email=settings.admin_email.lower(),
                        password_hash=hash_password(password), is_admin=True))
            if settings.admin_password:
                log.warning("Created initial admin '%s' (password from ADMIN_PASSWORD).", settings.admin_username)
            else:
                log.warning("Created initial admin '%s' with generated password: %s  -- change it after first login.",
                            settings.admin_username, password)
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap()
    yield


app = FastAPI(title="User Access Management Portal", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(oauth.OAuthError, oauth.oauth_error_handler)
app.add_middleware(WebOriginsCORS)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(audit.router)
app.include_router(overview.router)
app.include_router(access_requests.public)
app.include_router(access_requests.router)
app.include_router(oauth.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


# In production, serve the built React app from the same origin as the API.
_dist = Path(settings.frontend_dist).resolve()
if (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "oauth/", ".well-known/")):
            raise HTTPException(404)
        file = (_dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(_dist):
            return FileResponse(file)
        return FileResponse(_dist / "index.html")
