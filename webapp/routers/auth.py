import secrets
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from auth import get_oauth_url, exchange_code, get_discord_user, create_session_token, verify_session_token, is_admin_user
from config import AUTH_REQUIRED
from services.online_tracker import ping, get_online_count, get_online_users

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 86400 * 7


@router.get("/auth/login")
async def login():
    state = secrets.token_urlsafe(16)
    url = get_oauth_url(state)
    return RedirectResponse(url)


@router.get("/auth/callback")
async def callback(code: str, state: str = ""):
    token_data = await exchange_code(code)
    if not token_data:
        return JSONResponse({"error": "Token exchange failed"}, status_code=400)

    access_token = token_data.get("access_token")
    if not access_token:
        return JSONResponse({"error": "No access token"}, status_code=400)

    discord_user = await get_discord_user(access_token)
    if not discord_user:
        return JSONResponse({"error": "Failed to get Discord user"}, status_code=400)

    session_token = create_session_token(discord_user)
    response = RedirectResponse("/")
    response.set_cookie(
        COOKIE_NAME, session_token,
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", secure=True,
    )
    return response


@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/")
    response.delete_cookie(COOKIE_NAME, secure=True)
    return response


@router.get("/auth/me")
async def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return {"authenticated": False, "auth_required": AUTH_REQUIRED}

    payload = verify_session_token(token)
    if not payload:
        return {"authenticated": False, "auth_required": AUTH_REQUIRED}

    ping(payload["sub"], payload.get("username", ""))

    avatar_url = ""
    if payload.get("avatar"):
        avatar_url = f"https://cdn.discordapp.com/avatars/{payload['sub']}/{payload['avatar']}.png?size=64"

    return {
        "authenticated": True,
        "auth_required": AUTH_REQUIRED,
        "user_id": payload["sub"],
        "username": payload.get("username", ""),
        "avatar_url": avatar_url,
        "is_admin": is_admin_user(payload["sub"]),
    }


@router.get("/auth/online")
async def online(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    user_id = ""
    if token:
        payload = verify_session_token(token)
        if payload:
            user_id = payload["sub"]
    if not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "count": get_online_count(),
        "users": get_online_users(),
    }
