from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONFIG_FILE = Path(
    os.getenv(
        "GE360_RUNTIME_CONFIG_FILE",
        "/var/lib/ge360-analitica/secrets/runtime_config.json",
    )
)

SECRET_KEYS = {
    "WORDPRESS_APP_PASSWORD",
    "WORDPRESS_GE360_KEY",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "META_APP_SECRET",
    "META_PAGE_ACCESS_TOKEN",
    "META_USER_ACCESS_TOKEN",
}

DEFAULTS = {
    "WORDPRESS_BASE_URL": "https://triesteincostruzione.com",
    "GOOGLE_REDIRECT_URI": "http://127.0.0.1:8788/api/oauth/google/callback",
    "SEARCH_CONSOLE_SITE_URL": "https://triesteincostruzione.com/",
    "META_GRAPH_VERSION": "v26.0",
}


def _load() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save(payload: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def get(key: str, default: str = "") -> str:
    payload = _load()
    value = payload.get(key)
    if value is not None and str(value).strip() != "":
        return str(value).strip()

    env_value = os.getenv(key, "")
    if env_value.strip():
        return env_value.strip()

    if key in DEFAULTS:
        return str(DEFAULTS[key])
    return default


def set_many(values: dict[str, Any]) -> dict[str, Any]:
    payload = _load()

    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        payload[key] = value

    _save(payload)
    return payload


def delete(keys: list[str]) -> None:
    payload = _load()
    changed = False
    for key in keys:
        if key in payload:
            payload.pop(key, None)
            changed = True
    if changed:
        _save(payload)


def masked_value(key: str) -> str:
    value = get(key)
    if not value:
        return ""
    if key not in SECRET_KEYS:
        return value
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:3]}••••••{value[-3:]}"


def has_value(key: str) -> bool:
    return bool(get(key))


def snapshot(keys: list[str]) -> dict[str, Any]:
    return {
        key: {
            "configured": has_value(key),
            "value": masked_value(key),
            "secret": key in SECRET_KEYS,
        }
        for key in keys
    }
