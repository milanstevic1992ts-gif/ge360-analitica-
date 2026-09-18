import os

import httpx


AGENT_SOCKET = os.getenv("GE360_AGENT_SOCKET", "/data/ge360-codex.sock")
AGENT_TIMEOUT = float(os.getenv("GE360_AGENT_TIMEOUT", "135"))


async def agent_health() -> dict:
    transport = httpx.AsyncHTTPTransport(uds=AGENT_SOCKET)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://ge360-agent",
        timeout=10,
    ) as client:
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()


async def ask_agent(question: str, context: dict) -> dict:
    transport = httpx.AsyncHTTPTransport(uds=AGENT_SOCKET)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://ge360-agent",
        timeout=AGENT_TIMEOUT,
    ) as client:
        response = await client.post(
            "/ask",
            json={"question": question, "context": context},
        )
        response.raise_for_status()
        return response.json()
