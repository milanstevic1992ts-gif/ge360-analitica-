import os
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


PROJECT_DIR = Path(os.getenv("GE360_PROJECT_DIR", Path(__file__).resolve().parents[1]))
WORKSPACE_DIR = PROJECT_DIR / "data" / "agent-workspace"
TIMEOUT_SECONDS = int(os.getenv("GE360_CODEX_TIMEOUT", "120"))

app = FastAPI(
    title="GE360 Codex CLI Bridge",
    version="0.1.0",
    description="Bridge locale tra GE360 Analitica e Codex CLI autenticato con ChatGPT.",
)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    context: dict = Field(default_factory=dict)


def codex_path() -> str | None:
    return shutil.which("codex")


def build_prompt(question: str, context: dict) -> str:
    import json

    safe_context = json.dumps(context, ensure_ascii=False, indent=2)
    return f"""Sei l'agente analitico di GE360 Analitica.

REGOLE:
- lavora solo in lettura;
- non modificare file;
- non tentare accessi a servizi esterni;
- usa come fonte primaria esclusivamente i dati aggregati forniti nel CONTEXT;
- se i dati non bastano, dichiaralo chiaramente;
- non inventare metriche, correlazioni o cause;
- rispondi in italiano, in modo operativo e sintetico;
- evidenzia numeri e confronti utili;
- non includere dati personali non necessari.

DOMANDA:
{question}

CONTEXT GE360:
{safe_context}
"""


@app.get("/health")
def health() -> dict:
    binary = codex_path()
    return {
        "status": "ok" if binary else "codex_missing",
        "codex_found": bool(binary),
        "codex_path": binary,
        "mode": "chatgpt_cli",
        "sandbox": "read-only",
    }


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    binary = codex_path()
    if not binary:
        raise HTTPException(status_code=503, detail="Codex CLI non trovato nel PATH del servizio")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(request.question, request.context)

    command = [
        binary,
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        prompt,
    ]

    try:
        result = subprocess.run(
            command,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Codex CLI ha superato il timeout") from exc

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "Errore sconosciuto").strip()
        raise HTTPException(status_code=502, detail=error[-3000:])

    answer = result.stdout.strip()
    if not answer:
        raise HTTPException(status_code=502, detail="Codex CLI non ha restituito una risposta")

    return {
        "ok": True,
        "provider": "codex-cli",
        "auth": "chatgpt",
        "sandbox": "read-only",
        "answer": answer,
    }
