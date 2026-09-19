from __future__ import annotations

import asyncio
from typing import Any

from .connectors.ga4 import GA4Connector
from .connectors.google_business import GoogleBusinessConnector
from .connectors.meta import MetaConnector
from .connectors.search_console import SearchConsoleConnector
from .connectors.wordpress import WordPressConnector
from .db import get_cursor, persist_result, reset_cursor, set_connector_state


CONNECTORS = {
    "wordpress": WordPressConnector,
    "ga4": GA4Connector,
    "search_console": SearchConsoleConnector,
    "google_business": GoogleBusinessConnector,
    "meta": MetaConnector,
}


HISTORY_PROVIDERS = ("ga4", "search_console", "google_business", "meta")

# Evita due sincronizzazioni dello stesso connettore in parallelo
# (es. storico in corso + sync automatica oraria).
_running: set[str] = set()


def running_providers() -> list[str]:
    return sorted(_running)


async def sync_provider(provider: str) -> dict[str, Any]:
    connector_cls = CONNECTORS.get(provider)
    if connector_cls is None:
        raise ValueError(f"Connettore non disponibile: {provider}")

    if provider in _running:
        return {
            "provider": provider,
            "ok": True,
            "skipped": True,
            "persisted": {"metrics": 0, "events": 0, "content_items": 0},
            "message": f"{provider}: sincronizzazione già in corso",
        }

    _running.add(provider)
    try:
        return await _sync_provider(provider, connector_cls)
    finally:
        _running.discard(provider)


async def restart_history(provider: str) -> dict[str, Any]:
    """Azzera il cursore e riscarica tutto lo storico disponibile."""
    if provider not in HISTORY_PROVIDERS:
        raise ValueError(f"Lo storico completo non è disponibile per {provider}")
    if provider in _running:
        return {"provider": provider, "started": False, "message": "Sincronizzazione già in corso"}

    reset_cursor(provider)
    set_connector_state(provider, "syncing", "Scaricamento storico completo in corso…")
    return {"provider": provider, "started": True, "message": "Storico completo avviato"}


async def _sync_provider(provider: str, connector_cls) -> dict[str, Any]:

    connector = connector_cls()
    if not connector.configured():
        message = f"{provider}: configurazione incompleta"
        set_connector_state(provider, "not_configured", message)
        return {
            "provider": provider,
            "ok": False,
            "persisted": {"metrics": 0, "events": 0, "content_items": 0},
            "message": message,
        }

    cursor = get_cursor(provider)

    try:
        result = await connector.sync(cursor=cursor)
        # Lo storico può essere di centinaia di migliaia di righe: si scrive
        # in un thread per non bloccare la dashboard durante il salvataggio.
        persisted = await asyncio.to_thread(persist_result, result)
    except Exception as exc:
        set_connector_state(provider, "error", str(exc))
        raise

    return {
        "provider": provider,
        "ok": result.ok,
        "cursor": result.cursor,
        "persisted": persisted,
        "message": result.message,
    }


async def sync_all() -> dict[str, Any]:
    results = []
    for provider in CONNECTORS:
        try:
            results.append(await sync_provider(provider))
        except Exception as exc:
            results.append(
                {
                    "provider": provider,
                    "ok": False,
                    "error": str(exc),
                }
            )

    return {
        "ok": all(item.get("ok", False) for item in results),
        "results": results,
    }
