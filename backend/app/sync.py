from __future__ import annotations

from typing import Any

from .connectors.wordpress import WordPressConnector
from .db import get_cursor, persist_result, set_connector_state


CONNECTORS = {
    "wordpress": WordPressConnector,
}


async def sync_provider(provider: str) -> dict[str, Any]:
    connector_cls = CONNECTORS.get(provider)
    if connector_cls is None:
        raise ValueError(f"Connettore non disponibile: {provider}")

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
        persisted = persist_result(result)
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
