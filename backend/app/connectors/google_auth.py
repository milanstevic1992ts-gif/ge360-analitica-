import os
import time

import httpx


class GoogleAuth:
    _access_token: str | None = None
    _expires_at: float = 0

    def __init__(self) -> None:
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")

    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    async def access_token(self) -> str:
        if not self.configured():
            raise RuntimeError(
                "Google OAuth incompleto: servono GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET e GOOGLE_REFRESH_TOKEN"
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
                    "refresh_token": self.refresh_token,
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
