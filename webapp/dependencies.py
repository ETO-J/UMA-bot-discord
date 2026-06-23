from fastapi import Request, HTTPException

from config import AUTH_REQUIRED
from auth import verify_session_token
from services.online_tracker import ping

COOKIE_NAME = "session"
DEFAULT_USER_ID = "local_user"


async def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = verify_session_token(token)
        if payload:
            ping(payload["sub"], payload.get("username", ""))
            return payload
    if AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return None


async def get_current_user_id(request: Request) -> str:
    user = await get_current_user(request)
    if user:
        return user["sub"]
    if AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return DEFAULT_USER_ID
