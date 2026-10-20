"""OpenID Connect provider: how company systems sign users in through the portal.

Flow (authorization code + PKCE):
  1. System redirects the browser to /oauth/authorize
  2. Portal signs the user in (or reuses the existing SSO session) and checks they
     hold at least one role in that system, then redirects back with a one-time code
  3. System's backend exchanges the code at /oauth/token for an ID token, an access
     token (both RS256 JWTs carrying a "roles" claim) and a refresh token
  4. System verifies tokens with the public keys from /oauth/jwks
"""

import base64
import secrets
import time
from datetime import timedelta
from urllib.parse import unquote, urlencode

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..database import get_db
from ..deps import audit, get_portal_session, terminate_user_sessions
from ..models import Application, AuthorizationCode, RefreshToken, User
from ..security import hash_token, new_token, signing_keys, to_epoch, utcnow, verify_pkce

router = APIRouter(tags=["oidc"])

SUPPORTED_SCOPES = {"openid", "profile", "email", "roles", "offline_access"}


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status: int = 400):
        self.error, self.description, self.status = error, description, status


def oauth_error_handler(_request: Request, exc: OAuthError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Basic"} if exc.status == 401 else None
    return JSONResponse({"error": exc.error, "error_description": exc.description},
                        status_code=exc.status, headers=headers)


def _with_params(uri: str, params: dict) -> str:
    return uri + ("&" if "?" in uri else "?") + urlencode(params)


def _client_by_id(db: DbSession, client_id: str | None) -> Application | None:
    if not client_id:
        return None
    return db.scalar(select(Application).where(Application.client_id == client_id))


# ---------------------------------------------------------------- discovery

@router.get("/.well-known/openid-configuration")
def discovery():
    base = settings.issuer
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "userinfo_endpoint": f"{base}/oauth/userinfo",
        "jwks_uri": f"{base}/oauth/jwks",
        "end_session_endpoint": f"{base}/oauth/logout",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": sorted(SUPPORTED_SCOPES),
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256"],
        "claims_supported": ["sub", "name", "preferred_username", "email", "roles", "permissions", "auth_time", "nonce"],
    }


@router.get("/oauth/jwks")
def jwks():
    return {"keys": [signing_keys.public_jwk()]}


@router.get("/oauth/public-key.pem")
def public_key_pem():
    """The same public key as JWKS, as a PEM file. Apps save it (e.g. portal_public_key.pem) and verify
    tokens with it locally. It can only check signatures, never create them, so it isn't secret."""
    return Response(
        signing_keys.public_pem(), media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="portal_public_key.pem"'},
    )


# ---------------------------------------------------------------- authorize

@router.get("/oauth/authorize")
def authorize(
    request: Request,
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    scope: str = "openid",
    state: str | None = None,
    nonce: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    prompt: str | None = None,
    db: DbSession = Depends(get_db),
):
    app = _client_by_id(db, client_id)
    # Never redirect to an unverified URI: these errors are shown, not sent back.
    if not app or not app.is_active:
        raise HTTPException(400, "Unknown or inactive client_id")
    if redirect_uri not in app.redirect_uris:
        raise HTTPException(400, "redirect_uri is not registered for this application")

    def error(code: str, description: str) -> RedirectResponse:
        params = {"error": code, "error_description": description}
        if state:
            params["state"] = state
        return RedirectResponse(_with_params(redirect_uri, params), status_code=302)

    if response_type != "code":
        return error("unsupported_response_type", "Only response_type=code is supported")
    # S256 is the only method supported, so it's assumed when the app doesn't name one.
    if code_challenge and (code_challenge_method or "S256") != "S256":
        return error("invalid_request", "Only code_challenge_method=S256 is supported")
    if not app.is_confidential and not code_challenge:
        return error("invalid_request", "PKCE is required for public clients")
    scopes = [s for s in scope.split() if s in SUPPORTED_SCOPES]

    session = get_portal_session(request, db)
    if session is None:
        if prompt == "none":
            return error("login_required", "User is not signed in")
        next_url = f"{request.url.path}?{request.url.query}"
        return RedirectResponse(f"{settings.frontend_url}/login?" + urlencode({"next": next_url}), 302)

    user = session.user
    if user.must_change_password:
        # First sign-in with a password an admin set: no system gets a sign-in until the user picks
        # their own. The portal page sends them back here afterwards to finish signing in.
        if prompt == "none":
            return error("interaction_required", "User must change their password")
        next_url = f"{request.url.path}?{request.url.query}"
        return RedirectResponse(f"{settings.frontend_url}/change-password?" + urlencode({"next": next_url}), 302)

    if not user.roles_in(app.id):
        audit(db, user, "sso.denied", target=app.name, detail="no role in application", request=request)
        db.commit()
        if prompt == "none":  # silent check: no portal UI, report back to the system instead
            return error("access_denied", "User has no role in this application")
        return RedirectResponse(f"{settings.frontend_url}/access-denied?" + urlencode({"app": app.name}), 302)

    code = new_token()
    db.add(
        AuthorizationCode(
            code_hash=hash_token(code),
            application_id=app.id,
            user_id=user.id,
            redirect_uri=redirect_uri,
            scope=" ".join(scopes),
            nonce=nonce,
            code_challenge=code_challenge,
            auth_time=session.created_at,
            expires_at=utcnow() + timedelta(seconds=settings.auth_code_ttl_seconds),
        )
    )
    audit(db, user, "sso.authorize", target=app.name, request=request)
    db.commit()

    params = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(_with_params(redirect_uri, params), status_code=302)


# ---------------------------------------------------------------- token

def _authenticate_client(request: Request, db: DbSession, client_id: str | None,
                         client_secret: str | None) -> Application:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            basic_id, basic_secret = decoded.split(":", 1)
        except ValueError:
            raise OAuthError("invalid_client", "Malformed Basic authorization header", 401)
        client_id, client_secret = unquote(basic_id), unquote(basic_secret)

    app = _client_by_id(db, client_id)
    if not app or not app.is_active:
        raise OAuthError("invalid_client", "Unknown or inactive client", 401)
    if app.is_confidential:
        if not client_secret or not secrets.compare_digest(hash_token(client_secret), app.client_secret_hash):
            raise OAuthError("invalid_client", "Client authentication failed", 401)
    return app


def _issue_tokens(db: DbSession, app: Application, user: User, scope: str,
                  auth_time, nonce: str | None = None) -> JSONResponse:
    roles = user.roles_in(app.id)
    now = int(time.time())
    ttl = settings.access_token_ttl_minutes * 60
    identity = {
        "preferred_username": user.username,
        "name": user.display_name,  # full name (standard OIDC); the username is preferred_username
        "email": user.email,
        "roles": roles,
        "permissions": user.permissions_in(app.id),
    }
    access_token = signing_keys.sign({
        "iss": settings.issuer, "sub": str(user.id), "aud": app.client_id, "client_id": app.client_id,
        "iat": now, "exp": now + ttl, "jti": new_token(16), "scope": scope, **identity,
    })
    body = {"access_token": access_token, "token_type": "Bearer", "expires_in": ttl, "scope": scope}

    if "openid" in scope.split():
        id_claims = {
            "iss": settings.issuer, "sub": str(user.id), "aud": app.client_id,
            "iat": now, "exp": now + ttl, "auth_time": to_epoch(auth_time), **identity,
        }
        if nonce:
            id_claims["nonce"] = nonce
        body["id_token"] = signing_keys.sign(id_claims)

    refresh = new_token()
    db.add(
        RefreshToken(
            token_hash=hash_token(refresh), application_id=app.id, user_id=user.id, scope=scope,
            auth_time=auth_time,
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    body["refresh_token"] = refresh
    db.commit()
    return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.post("/oauth/token")
def token(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    db: DbSession = Depends(get_db),
):
    app = _authenticate_client(request, db, client_id, client_secret)

    if grant_type == "authorization_code":
        record = db.get(AuthorizationCode, hash_token(code or ""))
        if not record or record.application_id != app.id or record.expires_at < utcnow():
            raise OAuthError("invalid_grant", "Authorization code is invalid or expired")
        db.delete(record)  # single use
        db.commit()
        if record.redirect_uri != redirect_uri:
            raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request")
        if record.code_challenge and not (code_verifier and verify_pkce(code_verifier, record.code_challenge)):
            raise OAuthError("invalid_grant", "PKCE verification failed")
        user = db.get(User, record.user_id)
        if not user or not user.is_active or not user.roles_in(app.id):
            raise OAuthError("invalid_grant", "User no longer has access to this application")
        return _issue_tokens(db, app, user, record.scope, record.auth_time, record.nonce)

    if grant_type == "refresh_token":
        record = db.get(RefreshToken, hash_token(refresh_token or ""))
        if not record or record.revoked or record.application_id != app.id or record.expires_at < utcnow():
            raise OAuthError("invalid_grant", "Refresh token is invalid, expired or revoked")
        record.revoked = True  # rotation: each refresh token works once
        db.commit()
        user = db.get(User, record.user_id)
        # Roles are re-read here, so role changes reach systems on the next refresh.
        if not user or not user.is_active or not user.roles_in(app.id):
            raise OAuthError("invalid_grant", "User no longer has access to this application")
        return _issue_tokens(db, app, user, record.scope, record.auth_time)

    raise OAuthError("unsupported_grant_type", f"grant_type '{grant_type}' is not supported")


@router.post("/oauth/revoke")
def revoke(
    request: Request,
    token: str = Form(...),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    db: DbSession = Depends(get_db),
):
    app = _authenticate_client(request, db, client_id, client_secret)
    record = db.get(RefreshToken, hash_token(token))
    if record and record.application_id == app.id:
        record.revoked = True
        db.commit()
    return JSONResponse({})  # RFC 7009: always 200


# ---------------------------------------------------------------- userinfo

@router.api_route("/oauth/userinfo", methods=["GET", "POST"])
def userinfo(request: Request, db: DbSession = Depends(get_db)):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise OAuthError("invalid_token", "Bearer token required", 401)
    try:
        claims = signing_keys.verify(auth[7:])
    except jwt.PyJWTError as exc:
        raise OAuthError("invalid_token", str(exc), 401)
    user = db.get(User, int(claims["sub"]))
    app = _client_by_id(db, claims.get("client_id"))
    if not user or not user.is_active or not app:
        raise OAuthError("invalid_token", "Token subject or client no longer valid", 401)
    return {
        "sub": str(user.id),
        "preferred_username": user.username,
        "name": user.display_name,
        "email": user.email,
        "roles": user.roles_in(app.id),
        "permissions": user.permissions_in(app.id),
    }


# ---------------------------------------------------------------- logout

@router.get("/oauth/logout")
def end_session(
    request: Request,
    post_logout_redirect_uri: str | None = None,
    client_id: str | None = None,
    state: str | None = None,
    db: DbSession = Depends(get_db),
):
    """Single sign-out: ends the portal session and revokes the user's refresh tokens."""
    session = get_portal_session(request, db)
    if session:
        audit(db, session.user, "logout", target=session.user.username, detail="via SSO end_session",
              request=request)
        terminate_user_sessions(db, session.user_id)
        db.commit()

    target = f"{settings.frontend_url}/login"
    app = _client_by_id(db, client_id)
    if app and post_logout_redirect_uri and post_logout_redirect_uri in [*app.redirect_uris, app.home_url]:
        target = _with_params(post_logout_redirect_uri, {"state": state}) if state else post_logout_redirect_uri

    response = RedirectResponse(target, status_code=302)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
