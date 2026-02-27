import datetime

import httpx
import jwt

from config.auth import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    SESSION_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    SUPER_ADMIN_EMAIL,
    APP_URL,
)


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def get_google_redirect_uri():
    return f"{APP_URL}/auth/callback"


def get_google_auth_url():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": get_google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{qs}"


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for Google user info."""
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": get_google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise Exception(f"Token exchange failed: {token_resp.text}")

        tokens = token_resp.json()
        access_token = tokens["access_token"]

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise Exception(f"Userinfo fetch failed: {userinfo_resp.text}")

        return userinfo_resp.json()


def create_jwt(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def is_super_admin(email: str) -> bool:
    return email.lower() == SUPER_ADMIN_EMAIL.lower()


# ===== Gmail OAuth Connect (per-user) =====

GMAIL_CONNECT_SCOPES = "openid email profile https://www.googleapis.com/auth/gmail.readonly"


def get_gmail_connect_url(state: str = "") -> str:
    """Build Google OAuth URL for Gmail access with offline refresh_token."""
    from urllib.parse import urlencode

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{APP_URL}/auth/gmail/callback",
        "response_type": "code",
        "scope": GMAIL_CONNECT_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_gmail_code(code: str) -> dict:
    """Exchange Gmail authorization code for tokens + user info.
    Returns {access_token, refresh_token, email, name, picture}."""
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{APP_URL}/auth/gmail/callback",
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise Exception(f"Gmail token exchange failed: {token_resp.text}")

        tokens = token_resp.json()

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise Exception(f"Gmail userinfo failed: {userinfo_resp.text}")

        user = userinfo_resp.json()
        return {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "picture": user.get("picture", ""),
        }
