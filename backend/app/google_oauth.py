import os
import secrets
from urllib.parse import urlencode

import httpx

from .connectors.google_auth import GoogleAuth
from .config_store import get as config_get


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/business.manage",
]

_pending_states: set[str] = set()


def configured() -> bool:
    return bool(
        config_get("GOOGLE_CLIENT_ID")
        and config_get("GOOGLE_CLIENT_SECRET")
        and config_get("GOOGLE_REDIRECT_URI")
    )


def authorization_url() -> str:
    if not configured():
        raise RuntimeError(
            "Configura GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e GOOGLE_REDIRECT_URI"
        )

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = {
        "client_id": config_get("GOOGLE_CLIENT_ID"),
        "redirect_uri": config_get("GOOGLE_REDIRECT_URI"),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, state: str) -> dict:
    if state not in _pending_states:
        raise RuntimeError("Stato OAuth Google non valido o scaduto")

    _pending_states.discard(state)

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": config_get("GOOGLE_CLIENT_ID"),
                "client_secret": config_get("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": config_get("GOOGLE_REDIRECT_URI"),
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        payload = response.json()

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "Google non ha restituito un refresh token. "
            "Riprova il collegamento e autorizza nuovamente l'accesso."
        )

    GoogleAuth.save_refresh_token(
        refresh_token,
        metadata={
            "scope": payload.get("scope", ""),
            "token_type": payload.get("token_type", ""),
        },
    )

    return {
        "ok": True,
        "scopes": payload.get("scope", "").split(),
    }


def disconnect() -> None:
    GoogleAuth.disconnect()
