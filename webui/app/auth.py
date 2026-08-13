import os
import secrets

from fastapi import Cookie, Header, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "md_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
_SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

_serializer = URLSafeTimedSerializer(_SECRET_KEY, salt="md-webui-session")


def auth_enabled() -> bool:
    return bool(APP_PASSWORD)


def check_password(password: str) -> bool:
    return auth_enabled() and secrets.compare_digest(password, APP_PASSWORD)


def make_session_cookie(response: Response) -> None:
    token = _serializer.dumps({"ok": True})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def _cookie_is_valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def require_auth(
    md_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency guarding protected routes.

    Accepts either the browser session cookie (set after /login), or an
    `Authorization: Bearer <APP_PASSWORD>` header for scripted/API access.
    """
    if not auth_enabled():
        return
    if _cookie_is_valid(md_session):
        return
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if secrets.compare_digest(token, APP_PASSWORD):
            return
    raise HTTPException(status_code=401, detail="Not authenticated")


def is_authenticated(md_session: str | None) -> bool:
    if not auth_enabled():
        return True
    return _cookie_is_valid(md_session)
