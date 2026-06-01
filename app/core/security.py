from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from app.config import settings


class AutoCRMAuth:
    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_token(self) -> str:
        if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
            return self._token

        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/auth/login",
                json={
                    "email": settings.autocrm_auth_email,
                    "password": settings.autocrm_auth_password,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._token = data.get("access_token") or ""
            self._expires_at = datetime.utcnow() + timedelta(minutes=55)
            return self._token
