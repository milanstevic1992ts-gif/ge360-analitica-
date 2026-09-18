import json
import os
import time
from pathlib import Path

import httpx


TOKEN_FILE = Path(
    os.getenv("GE360_GOOGLE_TOKEN_FILE", "/data/secrets/google_oauth.json")
)


class GoogleAuth:
    _access_token: str | None = None
    _expires_at: float = 0

    def __init__(self) -> None:
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    def _stored_refresh_token(self) -> str:
        env_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
        if env_token:
            return env_token

        if not TOKEN_FILE.exists():
            return ""

        try:
            payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            return str(payload.get("refresh_token", "")).strip()
        except Exception:
            return ""

    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self._stored_refresh_token()
        )

    @staticmethod
    def save_refresh_token(refresh_token: str, metadata: dict | None = None) -> None:
        if not refresh_token:
            raise ValueError("refresh_token vuoto")

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "refresh_token": refresh_token,
            "saved_at": int(time.time()),
        }
        if metadata:
            payload.update(metadata)

        TOKEN_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass

        GoogleAuth._access_token = None
        GoogleAuth._expires_at = 0

    @staticmethod
    def disconnect() -> None:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        GoogleAuth._access_token = None
        GoogleAuth._expires_at = 0

    async def access_token(self) -> str:
        refresh_token = self._stored_refresh_token()

        if not (self.client_id and self.client_secret and refresh_token):
            raise RuntimeError(
                "Google OAuth incompleto: configura client ID/secret e collega "
                "l'account Google dalla dashboard"
            )

        now = time.time()
        if self.__class__._access_token and now < self.__class__._expires_at - 60:
            return self.__class__._access_token

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            payload = response.json()

        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Google non ha restituito access_token")

        self.__class__._access_token = token
        self.__class__._expires_at = now + int(payload.get("expires_in", 3600))
        return token

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.access_token()}"}
