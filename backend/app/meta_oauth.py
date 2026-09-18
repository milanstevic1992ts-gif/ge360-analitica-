from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from .config_store import get, set_many


_pending_states: set[str] = set()

META_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_manage_insights",
]


class MetaPageSelectionRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=200)


class MetaSessionRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=10000)
    user_id: str = Field(default="", max_length=200)
    expires_in: int | None = Field(default=None, ge=0, le=31536000)
    data_access_expiration_time: int | None = Field(default=None, ge=0)


def _version() -> str:
    return get("META_GRAPH_VERSION", "v26.0") or "v26.0"


def sdk_configured() -> bool:
    """The browser Facebook Login flow only needs the public Meta App ID."""
    return bool(get("META_APP_ID"))


def server_oauth_configured() -> bool:
    """Legacy authorization-code flow: kept as an optional advanced fallback."""
    return bool(get("META_APP_ID") and get("META_APP_SECRET"))


def configured() -> bool:
    # Backwards compatible name used by older code/tests.
    return server_oauth_configured()


def redirect_uri() -> str:
    return get(
        "META_REDIRECT_URI",
        "http://127.0.0.1:8788/api/oauth/meta/callback",
    )


def public_config() -> dict:
    config_id = get("META_BUSINESS_LOGIN_CONFIG_ID")
    return {
        "app_id": get("META_APP_ID"),
        "graph_version": _version(),
        "scopes": META_SCOPES,
        "sdk_ready": sdk_configured(),
        "server_oauth_ready": server_oauth_configured(),
        "business_login_ready": bool(config_id),
        "business_login_config_id": config_id,
        "redirect_uri": redirect_uri(),
    }


def authorization_url() -> str:
    if not server_oauth_configured():
        raise RuntimeError(
            "Il login OAuth server richiede App ID e App Secret. "
            "Per il percorso normale usa Accedi con Facebook (App ID soltanto)."
        )

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = {
        "client_id": get("META_APP_ID"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "response_type": "code",
    }

    config_id = get("META_BUSINESS_LOGIN_CONFIG_ID")
    if config_id:
        # Facebook Login for Business usa una Configuration ID creata nella
        # dashboard Meta. I permessi vivono nella configurazione, non nell'URL.
        params["config_id"] = config_id
    else:
        # Fallback per app legacy/classic Facebook Login.
        params["scope"] = ",".join(META_SCOPES)

    return (
        f"https://www.facebook.com/{_version()}/dialog/oauth?"
        f"{urlencode(params)}"
    )


async def _exchange_code(code: str) -> str:
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(
            f"https://graph.facebook.com/{_version()}/oauth/access_token",
            params={
                "client_id": get("META_APP_ID"),
                "client_secret": get("META_APP_SECRET"),
                "redirect_uri": redirect_uri(),
                "code": code,
            },
        )
        response.raise_for_status()
        payload = response.json()

        short_token = str(payload.get("access_token") or "")
        if not short_token:
            raise RuntimeError("Meta non ha restituito un access token")

        # Con App Secret disponibile proviamo a ottenere un token utente long-lived.
        try:
            long_response = await client.get(
                f"https://graph.facebook.com/{_version()}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": get("META_APP_ID"),
                    "client_secret": get("META_APP_SECRET"),
                    "fb_exchange_token": short_token,
                },
            )
            long_response.raise_for_status()
            long_payload = long_response.json()
            return str(long_payload.get("access_token") or short_token)
        except Exception:
            return short_token


async def exchange_code(code: str, state: str) -> dict:
    if state not in _pending_states:
        raise RuntimeError("Stato OAuth Meta non valido o scaduto")

    _pending_states.discard(state)
    token = await _exchange_code(code)
    set_many({"META_USER_ACCESS_TOKEN": token})

    pages = await list_pages()
    if len(pages) == 1:
        await select_page(pages[0]["id"])
        return {"ok": True, "auto_selected": True, "pages": pages}

    return {"ok": True, "auto_selected": False, "pages": pages}


async def connect_browser_session(request: MetaSessionRequest) -> dict:
    """Accept a token returned by the official Facebook JavaScript SDK.

    No Meta App Secret is required. The token is validated by asking Graph API
    for the authenticated profile before it is persisted.
    """
    token = request.access_token.strip()

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        profile_response = await client.get(
            f"https://graph.facebook.com/{_version()}/me",
            params={
                "fields": "id,name",
                "access_token": token,
            },
        )
        profile_response.raise_for_status()
        profile = profile_response.json()

        profile_id = str(profile.get("id") or "")
        if not profile_id:
            raise RuntimeError("Meta non ha restituito l'identità del profilo Facebook")
        if request.user_id and request.user_id != profile_id:
            raise RuntimeError("Il token Facebook non corrisponde al profilo dichiarato")

        granted: list[str] = []
        declined: list[str] = []
        try:
            permissions_response = await client.get(
                f"https://graph.facebook.com/{_version()}/me/permissions",
                params={"access_token": token},
            )
            permissions_response.raise_for_status()
            for item in permissions_response.json().get("data", []):
                permission = str(item.get("permission") or "")
                status = str(item.get("status") or "")
                if not permission:
                    continue
                if status == "granted":
                    granted.append(permission)
                elif status == "declined":
                    declined.append(permission)
        except Exception:
            # Permissions are useful diagnostics, but they must not make a
            # valid login fail.
            pass

    expires_at = ""
    if request.expires_in:
        expires_at = str(int(time.time()) + int(request.expires_in))

    set_many(
        {
            "META_USER_ACCESS_TOKEN": token,
            "META_USER_ID": profile_id,
            "META_USER_NAME": str(profile.get("name") or ""),
            "META_TOKEN_EXPIRES_AT": expires_at,
            "META_DATA_ACCESS_EXPIRES_AT": (
                str(request.data_access_expiration_time)
                if request.data_access_expiration_time
                else ""
            ),
        }
    )

    pages = await list_pages()

    return {
        "ok": True,
        "profile": {
            "id": profile_id,
            "name": profile.get("name"),
        },
        "permissions": {
            "granted": sorted(set(granted)),
            "declined": sorted(set(declined)),
            "requested": META_SCOPES,
        },
        "pages": pages,
        "expires_at": expires_at or None,
    }


async def list_pages() -> list[dict]:
    token = get("META_USER_ACCESS_TOKEN")
    if not token:
        return []

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(
            f"https://graph.facebook.com/{_version()}/me/accounts",
            params={
                "fields": (
                    "id,name,access_token,category,"
                    "instagram_business_account{id,username,followers_count,media_count}"
                ),
                "limit": 100,
                "access_token": token,
            },
        )
        response.raise_for_status()
        payload = response.json()

    pages = []
    for item in payload.get("data", []):
        ig = item.get("instagram_business_account") or {}
        pages.append(
            {
                "id": str(item.get("id") or ""),
                "name": item.get("name"),
                "category": item.get("category"),
                "instagram": {
                    "connected": bool(ig.get("id")),
                    "id": str(ig.get("id") or "") or None,
                    "username": ig.get("username"),
                    "followers_count": ig.get("followers_count"),
                    "media_count": ig.get("media_count"),
                },
            }
        )
    return pages


async def _page_details(page_id: str) -> dict:
    token = get("META_USER_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Sessione Facebook non disponibile. Rifai Accedi con Facebook.")

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        accounts = await client.get(
            f"https://graph.facebook.com/{_version()}/me/accounts",
            params={
                "fields": (
                    "id,name,access_token,category,"
                    "instagram_business_account{id,username,followers_count,media_count}"
                ),
                "limit": 100,
                "access_token": token,
            },
        )
        accounts.raise_for_status()
        payload = accounts.json()

    for item in payload.get("data", []):
        if str(item.get("id")) == page_id:
            return item

    raise RuntimeError("Pagina Facebook non trovata tra quelle autorizzate")


async def select_page(page_id: str) -> dict:
    page = await _page_details(page_id)
    page_token = str(page.get("access_token") or "")
    if not page_token:
        raise RuntimeError("Meta non ha restituito il Page Access Token")

    ig = page.get("instagram_business_account") or {}

    set_many(
        {
            "META_PAGE_ID": str(page.get("id") or page_id),
            "META_PAGE_NAME": str(page.get("name") or ""),
            "META_PAGE_ACCESS_TOKEN": page_token,
            "META_INSTAGRAM_ACCOUNT_ID": str(ig.get("id") or ""),
            "META_INSTAGRAM_USERNAME": str(ig.get("username") or ""),
        }
    )

    return {
        "ok": True,
        "facebook_profile": {
            "id": get("META_USER_ID") or None,
            "name": get("META_USER_NAME") or None,
        },
        "facebook_page": {
            "id": str(page.get("id") or page_id),
            "name": page.get("name"),
            "category": page.get("category"),
        },
        "instagram": {
            "connected": bool(ig.get("id")),
            "id": str(ig.get("id") or "") or None,
            "username": ig.get("username"),
            "followers_count": ig.get("followers_count"),
            "media_count": ig.get("media_count"),
        },
    }


def disconnect() -> None:
    set_many(
        {
            "META_USER_ACCESS_TOKEN": "",
            "META_USER_ID": "",
            "META_USER_NAME": "",
            "META_TOKEN_EXPIRES_AT": "",
            "META_DATA_ACCESS_EXPIRES_AT": "",
            "META_PAGE_ID": "",
            "META_PAGE_NAME": "",
            "META_PAGE_ACCESS_TOKEN": "",
            "META_INSTAGRAM_ACCOUNT_ID": "",
            "META_INSTAGRAM_USERNAME": "",
        }
    )
