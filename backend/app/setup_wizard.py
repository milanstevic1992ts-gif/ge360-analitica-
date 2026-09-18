from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from . import local_ai
from .config_store import get, has_value, set_many, snapshot
from .connectors.google_auth import GoogleAuth
from .connectors.meta import MetaConnector
from .connectors.wordpress import WordPressConnector


class WordPressSetupRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=300)
    username: str = Field(default="", max_length=200)
    app_password: str = Field(default="", max_length=500)
    ge360_key: str = Field(default="", max_length=500)


class GoogleSetupRequest(BaseModel):
    client_id: str = Field(default="", max_length=500)
    client_secret: str = Field(default="", max_length=500)
    ga4_property_id: str = Field(default="", max_length=100)
    search_console_site_url: str = Field(default="", max_length=500)
    business_location_name: str = Field(default="", max_length=300)


class MetaSetupRequest(BaseModel):
    app_id: str = Field(default="", max_length=200)
    app_secret: str = Field(default="", max_length=500)
    page_id: str = Field(min_length=1, max_length=200)
    page_access_token: str = Field(min_length=10, max_length=5000)
    instagram_account_id: str = Field(default="", max_length=200)
    graph_version: str = Field(default="v26.0", max_length=20)


def _completion() -> dict[str, bool]:
    return {
        "ai": False,
        "wordpress": bool(get("WORDPRESS_BASE_URL") and get("WORDPRESS_GE360_KEY")),
        "google_credentials": bool(
            get("GOOGLE_CLIENT_ID") and get("GOOGLE_CLIENT_SECRET")
        ),
        "google_connected": GoogleAuth().configured(),
        "google_resources": bool(
            get("GA4_PROPERTY_ID")
            or get("SEARCH_CONSOLE_SITE_URL")
            or get("GOOGLE_BUSINESS_LOCATION_NAME")
        ),
        "meta": bool(get("META_PAGE_ID") and get("META_PAGE_ACCESS_TOKEN")),
    }


async def status() -> dict[str, Any]:
    ai_status = await local_ai.status()
    completion = _completion()
    completion["ai"] = bool(
        ai_status.get("ok") and ai_status.get("selected_available")
    )

    done = sum(1 for value in completion.values() if value)
    total = len(completion)

    return {
        "completion": completion,
        "done": done,
        "total": total,
        "percent": round(done / total * 100) if total else 0,
        "ai": ai_status,
        "wordpress": snapshot(
            [
                "WORDPRESS_BASE_URL",
                "WORDPRESS_USERNAME",
                "WORDPRESS_APP_PASSWORD",
                "WORDPRESS_GE360_KEY",
            ]
        ),
        "google": snapshot(
            [
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "GA4_PROPERTY_ID",
                "SEARCH_CONSOLE_SITE_URL",
                "GOOGLE_BUSINESS_LOCATION_NAME",
            ]
        ),
        "meta": snapshot(
            [
                "META_APP_ID",
                "META_APP_SECRET",
                "META_PAGE_ID",
                "META_PAGE_ACCESS_TOKEN",
                "META_INSTAGRAM_ACCOUNT_ID",
                "META_GRAPH_VERSION",
            ]
        ),
    }


async def save_and_test_wordpress(request: WordPressSetupRequest) -> dict[str, Any]:
    set_many(
        {
            "WORDPRESS_BASE_URL": request.base_url.rstrip("/"),
            "WORDPRESS_USERNAME": request.username,
            "WORDPRESS_APP_PASSWORD": request.app_password,
            "WORDPRESS_GE360_KEY": request.ge360_key,
        }
    )

    connector = WordPressConnector()
    result = await connector.sync()

    tracker_configured = bool(request.ge360_key)
    return {
        "ok": result.ok,
        "message": result.message,
        "tracker_configured": tracker_configured,
        "metrics": result.metrics,
    }


def save_google(request: GoogleSetupRequest) -> dict[str, Any]:
    values = {
        "GOOGLE_CLIENT_ID": request.client_id,
        "GOOGLE_CLIENT_SECRET": request.client_secret,
        "GA4_PROPERTY_ID": request.ga4_property_id,
        "SEARCH_CONSOLE_SITE_URL": request.search_console_site_url,
        "GOOGLE_BUSINESS_LOCATION_NAME": request.business_location_name,
        "GOOGLE_REDIRECT_URI": "http://127.0.0.1:8788/api/oauth/google/callback",
    }
    set_many(values)
    return {
        "ok": True,
        "oauth_ready": bool(request.client_id and request.client_secret),
        "saved": snapshot(list(values.keys())),
    }


async def discover_google_resources() -> dict[str, Any]:
    auth = GoogleAuth()
    if not auth.configured():
        raise RuntimeError(
            "Google non è ancora collegato. Salva Client ID/Secret e completa il login Google."
        )

    headers = await auth.headers()
    result: dict[str, Any] = {
        "ga4_properties": [],
        "search_console_sites": [],
        "business_accounts": [],
        "business_locations": [],
        "errors": {},
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            response = await client.get(
                "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                headers=headers,
                params={"pageSize": 200},
            )
            response.raise_for_status()
            payload = response.json()
            for account in payload.get("accountSummaries", []):
                account_name = account.get("displayName") or account.get("account")
                for prop in account.get("propertySummaries", []):
                    property_name = str(prop.get("property") or "")
                    result["ga4_properties"].append(
                        {
                            "id": property_name.replace("properties/", ""),
                            "name": prop.get("displayName"),
                            "account": account_name,
                            "property": property_name,
                        }
                    )
        except Exception as exc:
            result["errors"]["ga4"] = str(exc)

        try:
            response = await client.get(
                "https://www.googleapis.com/webmasters/v3/sites",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            result["search_console_sites"] = [
                {
                    "url": item.get("siteUrl"),
                    "permission": item.get("permissionLevel"),
                }
                for item in payload.get("siteEntry", [])
            ]
        except Exception as exc:
            result["errors"]["search_console"] = str(exc)

        try:
            response = await client.get(
                "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            accounts = payload.get("accounts", [])
            result["business_accounts"] = [
                {
                    "name": item.get("name"),
                    "account_name": item.get("accountName"),
                    "type": item.get("type"),
                }
                for item in accounts
            ]

            for account in accounts:
                account_name = str(account.get("name") or "")
                if not account_name:
                    continue
                try:
                    locations_response = await client.get(
                        "https://mybusinessbusinessinformation.googleapis.com/v1/"
                        f"{account_name}/locations",
                        headers=headers,
                        params={
                            "readMask": "name,title,storeCode,metadata",
                            "pageSize": 100,
                        },
                    )
                    locations_response.raise_for_status()
                    locations_payload = locations_response.json()
                    for location in locations_payload.get("locations", []):
                        result["business_locations"].append(
                            {
                                "name": location.get("name"),
                                "title": location.get("title"),
                                "store_code": location.get("storeCode"),
                                "place_id": (location.get("metadata") or {}).get("placeId"),
                                "account": account_name,
                            }
                        )
                except Exception as exc:
                    result["errors"][f"business_locations:{account_name}"] = str(exc)
        except Exception as exc:
            result["errors"]["business_accounts"] = str(exc)

    return result


async def save_and_test_meta(request: MetaSetupRequest) -> dict[str, Any]:
    set_many(
        {
            "META_APP_ID": request.app_id,
            "META_APP_SECRET": request.app_secret,
            "META_PAGE_ID": request.page_id,
            "META_PAGE_ACCESS_TOKEN": request.page_access_token,
            "META_INSTAGRAM_ACCOUNT_ID": request.instagram_account_id,
            "META_GRAPH_VERSION": request.graph_version or "v26.0",
        }
    )

    connector = MetaConnector()
    discovered = await connector.discover_accounts()

    return {
        "ok": True,
        "message": "Facebook collegato; verifica Instagram nel risultato.",
        **discovered,
    }
