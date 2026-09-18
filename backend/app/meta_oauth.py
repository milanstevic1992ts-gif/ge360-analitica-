from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from .config_store import get, set_many


_pending_states: set[str] = set()


class MetaPageSelectionRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=200)


def _version() -> str:
    return get("META_GRAPH_VERSION", "v26.0") or "v26.0"


def configured() -> bool:
    return bool(get("META_APP_ID") and get("META_APP_SECRET"))


def redirect_uri() -> str:
    return get(
        "META_REDIRECT_URI",
        "http://127.0.0.1:8788/api/oauth/meta/callback",
    )


def authorization_url() -> str:
    if not configured():
        raise RuntimeError(
            "Configura Meta App ID e App Secret una sola volta, poi usa Accedi con Facebook."
        )

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    scopes = [
        "pages_show_list",
        "pages_read_engagement",
        "read_insights",
        "instagram_basic",
        "instagram_manage_insights",
    ]

    params = {
        "client_id": get("META_APP_ID"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "response_type": "code",
        "scope": ",".join(scopes),
    }

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

        # Prova a convertire il token utente in long-lived.
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
            "META_PAGE_ACCESS_TOKEN": page_token,
            "META_INSTAGRAM_ACCOUNT_ID": str(ig.get("id") or ""),
        }
    )

    return {
        "ok": True,
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
            "META_PAGE_ID": "",
            "META_PAGE_ACCESS_TOKEN": "",
            "META_INSTAGRAM_ACCOUNT_ID": "",
        }
    )
