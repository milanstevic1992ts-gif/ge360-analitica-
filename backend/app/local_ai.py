from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from . import analytics
from .dashboard_service import dashboard
from .db import connect, utcnow


DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


class LocalAIConfigureRequest(BaseModel):
    base_url: str = Field(default=DEFAULT_BASE_URL, min_length=8, max_length=300)
    model: str = Field(min_length=1, max_length=200)
    think: bool = False


class LocalAIReportRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    report_type: str = Field(default="full", pattern="^(quick|full)$")


def _validate_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL Ollama non valida")

    host = (parsed.hostname or "").lower()
    allowed = {
        "127.0.0.1",
        "localhost",
        "::1",
    }

    if host not in allowed:
        raise ValueError(
            "Per sicurezza GE360 accetta Ollama locale su localhost/127.0.0.1"
        )

    return value


def settings() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT base_url, model, think, updated_at
            FROM local_ai_settings
            WHERE id = 1
            """
        ).fetchone()

    if row:
        return {
            "base_url": row["base_url"],
            "model": row["model"],
            "think": bool(row["think"]),
            "updated_at": row["updated_at"],
        }

    return {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "think": False,
        "updated_at": None,
    }


def save_settings(request: LocalAIConfigureRequest) -> dict[str, Any]:
    base_url = _validate_base_url(request.base_url)
    now = utcnow()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO local_ai_settings(id, base_url, model, think, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                base_url = excluded.base_url,
                model = excluded.model,
                think = excluded.think,
                updated_at = excluded.updated_at
            """,
            (
                base_url,
                request.model.strip(),
                1 if request.think else 0,
                now,
            ),
        )
        conn.commit()

    return settings()


async def _models(base_url: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        payload = response.json()

    result = []
    for item in payload.get("models", []):
        details = item.get("details") or {}
        result.append(
            {
                "name": item.get("name") or item.get("model"),
                "model": item.get("model") or item.get("name"),
                "size": item.get("size"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
                "family": details.get("family"),
            }
        )
    return result


async def status() -> dict[str, Any]:
    cfg = settings()
    base_url = _validate_base_url(cfg["base_url"])

    try:
        models = await _models(base_url)
        names = {item["name"] for item in models if item.get("name")}
        aliases = {item["model"] for item in models if item.get("model")}
        selected_available = cfg["model"] in names or cfg["model"] in aliases

        return {
            "ok": True,
            "provider": "ollama",
            "base_url": base_url,
            "selected_model": cfg["model"],
            "selected_available": selected_available,
            "think": cfg["think"],
            "models": models,
            "message": (
                "Ollama raggiungibile"
                if selected_available
                else "Ollama raggiungibile, ma il modello selezionato non è installato"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "ollama",
            "base_url": base_url,
            "selected_model": cfg["model"],
            "selected_available": False,
            "think": cfg["think"],
            "models": [],
            "message": f"Ollama non raggiungibile: {exc}",
        }


def _period_key(days: int) -> str:
    if days <= 7:
        return "7d"
    if days <= 30:
        return "30d"
    if days <= 90:
        return "90d"
    return "365d"


def build_analysis_context(days: int) -> dict[str, Any]:
    period = _period_key(days)
    dashboard_data = dashboard(period)

    return {
        "period_days": days,
        "dashboard_mode": dashboard_data.get("mode"),
        "kpis": dashboard_data.get("kpis", []),
        "trend": dashboard_data.get("trend", []),
        "sources": dashboard_data.get("sources", []),
        "funnel": dashboard_data.get("funnel", []),
        "top_content": dashboard_data.get("top_content", []),
        "deterministic_insights": dashboard_data.get("insights", []),
        "data_status": analytics.status(),
        "leads": analytics.leads_summary(days=days),
        "content_performance": analytics.content_performance(
            days=min(days, 365),
            limit=30,
        ),
        "anomalies": analytics.anomalies(
            days=min(days, 30),
            threshold_percent=20,
            limit=20,
        ),
        "local_seo": analytics.local_seo(
            days=min(days, 365),
            contains="trieste",
            limit=40,
        ),
        "opportunities": analytics.opportunity_radar(
            days=min(days, 365),
            min_views=10,
            limit=20,
        ),
    }


def _system_prompt(report_type: str) -> str:
    common = """
Sei GE360 Intelligence, analista locale per una piccola impresa edile a Trieste.
Ricevi esclusivamente dati già calcolati da GE360.

REGOLE:
- non inventare numeri, cause o correlazioni;
- distingui sempre FATTO, INTERPRETAZIONE e AZIONE;
- se i dati sono demo, incompleti o mancanti, dichiaralo;
- non confondere correlazione con causalità;
- non usare gergo inutile;
- scrivi in italiano;
- dai priorità a lead, conversioni, SEO locale, contenuti e acquisizione;
- quando proponi un'azione, spiega quale dato la giustifica.
""".strip()

    if report_type == "quick":
        return common + """

Produci un briefing operativo corto:
1. Quadro generale
2. Cosa è migliorato
3. Cosa è peggiorato
4. 3 azioni prioritarie
5. Dati mancanti / affidabilità
"""

    return common + """

Produci un report dettagliato in Markdown con queste sezioni:
# Sintesi esecutiva
# KPI principali
# Acquisizione e sorgenti
# Lead e conversioni
# Contenuti
# SEO locale
# Anomalie
# Opportunità
# Problemi / rischi
# Azioni consigliate ordinate per priorità
# Esperimenti da fare nei prossimi 7-30 giorni
# Dati mancanti e limiti dell'analisi

Alla fine aggiungi una sezione:
# Domande da approfondire con ChatGPT o Claude
con 5 domande intelligenti basate sui dati presenti.
"""


def _handoff_prompt(report: str, days: int, model: str) -> str:
    return f"""Agisci come analista senior di marketing locale e acquisizione clienti.

Qui sotto trovi un report generato dal mio sistema GE360 usando dati reali provenienti, quando disponibili, da WordPress, GA4, Search Console, Google Business Profile, Meta e tracking lead.

Il primo livello di analisi è stato eseguito localmente con Ollama / {model}.
Periodo analizzato: {days} giorni.

Voglio una seconda analisi critica:
- verifica se le conclusioni sono supportate dai dati;
- cerca pattern, anomalie e spiegazioni alternative;
- separa fatti da ipotesi;
- individua rischi e opportunità;
- proponi esperimenti concreti e misurabili;
- non inventare informazioni assenti.

REPORT GE360:

{report}
"""


async def _run_ollama(prompt: str, report_type: str) -> dict[str, Any]:
    cfg = settings()
    base_url = _validate_base_url(cfg["base_url"])

    payload = {
        "model": cfg["model"],
        "messages": [
            {
                "role": "system",
                "content": _system_prompt(report_type),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "think": cfg["think"],
        "keep_alive": "10m",
    }

    timeout = httpx.Timeout(300.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/chat", json=payload)
        response.raise_for_status()
        result = response.json()

    message = result.get("message") or {}
    answer = str(message.get("content") or "").strip()

    if not answer:
        raise RuntimeError("Ollama non ha restituito testo")

    return {
        "model": result.get("model") or cfg["model"],
        "answer": answer,
        "prompt_eval_count": result.get("prompt_eval_count"),
        "eval_count": result.get("eval_count"),
        "total_duration": result.get("total_duration"),
    }


async def generate_report(request: LocalAIReportRequest) -> dict[str, Any]:
    cfg_status = await status()
    if not cfg_status["ok"]:
        raise RuntimeError(cfg_status["message"])
    if not cfg_status["selected_available"]:
        raise RuntimeError(
            f"Il modello {cfg_status['selected_model']} non è installato in Ollama"
        )

    context = build_analysis_context(request.days)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    prompt = f"""Analizza i dati GE360 seguenti.

PERIODO: {request.days} giorni
TIPO REPORT: {request.report_type}

DATI:
{context_json}
"""

    result = await _run_ollama(prompt, request.report_type)
    handoff = _handoff_prompt(
        result["answer"],
        request.days,
        result["model"],
    )
    now = utcnow()

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ai_reports(
                report_type,
                period_days,
                model,
                report_markdown,
                handoff_prompt,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.report_type,
                request.days,
                result["model"],
                result["answer"],
                handoff,
                now,
            ),
        )
        report_id = cursor.lastrowid
        conn.commit()

    return {
        "id": report_id,
        "created_at": now,
        "report_type": request.report_type,
        "period_days": request.days,
        "model": result["model"],
        "report_markdown": result["answer"],
        "handoff_prompt": handoff,
        "usage": {
            "prompt_eval_count": result.get("prompt_eval_count"),
            "eval_count": result.get("eval_count"),
            "total_duration": result.get("total_duration"),
        },
        "dashboard_mode": context.get("dashboard_mode"),
    }


def reports(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, report_type, period_days, model, created_at
            FROM ai_reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def report(report_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                id, report_type, period_days, model,
                report_markdown, handoff_prompt, created_at
            FROM ai_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()

    return dict(row) if row else None
