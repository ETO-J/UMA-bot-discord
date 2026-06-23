import time
import logging
import traceback
from urllib.parse import quote
import httpx
from jose import jwt, JWTError

from config import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI, DISCORD_PROXY, JWT_SECRET, ADMIN_USER_ID

logger = logging.getLogger(__name__)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 86400 * 7
REQUEST_TIMEOUT = 15.0
MAX_RETRIES = 2

DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_BASE = "https://discord.com/api/v10"


def _client_kwargs():
    kwargs = {"timeout": REQUEST_TIMEOUT}
    if DISCORD_PROXY:
        kwargs["proxy"] = DISCORD_PROXY
    return kwargs


def get_oauth_url(state: str = "") -> str:
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
    }
    if state:
        params["state"] = state
    qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
    return f"{DISCORD_AUTH_URL}?{qs}"


async def exchange_code(code: str) -> dict | None:
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(**_client_kwargs()) as client:
                resp = await client.post(DISCORD_TOKEN_URL, data=data)
                if resp.status_code != 200:
                    logger.error("Discord token exchange failed (HTTP %s): %s", resp.status_code, resp.text)
                    logger.error("  redirect_uri used: %s", DISCORD_REDIRECT_URI)
                    return None
                return resp.json()
        except Exception as e:
            last_error = e
            logger.error("Token exchange error (attempt %s/%s): %s\n%s",
                         attempt + 1, MAX_RETRIES + 1, e, traceback.format_exc())
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))
    return None


async def get_discord_user(access_token: str) -> dict | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(**_client_kwargs()) as client:
                resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
                if resp.status_code != 200:
                    return None
                return resp.json()
        except Exception as e:
            last_error = e
            logger.error("Get user error (attempt %s/%s): %s\n%s",
                         attempt + 1, MAX_RETRIES + 1, e, traceback.format_exc())
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))
    return None


def create_session_token(discord_user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": discord_user["id"],
        "username": discord_user.get("username", ""),
        "avatar": discord_user.get("avatar") or "",
        "iat": now,
        "exp": now + JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def is_admin_user(user_id: str) -> bool:
    return user_id == ADMIN_USER_ID or user_id == "local_user"
