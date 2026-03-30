"""LibreLinkUp API client for FreeStyle Libre 2 glucose data."""

import hashlib
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# LibreLinkUp API headers — version 4.16.0+ required
LLU_HEADERS = {
    "Content-Type": "application/json",
    "product": "llu.android",
    "version": "4.16.0",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
    "Connection": "Keep-Alive",
}

# Regional API endpoints — note: api-us, not api (which is the global router)
REGION_MAP = {
    "us": "https://api-us.libreview.io",
    "eu": "https://api-eu.libreview.io",
    "au": "https://api-au.libreview.io",
    "de": "https://api-de.libreview.io",
    "fr": "https://api-fr.libreview.io",
}


class LibreLinkUpClient:
    """Client for the LibreLinkUp sharing API."""

    def __init__(self):
        self._token: str | None = None
        self._account_id_hash: str | None = None
        self._patient_id: str | None = None
        self._base_url = REGION_MAP.get(settings.libre_region, REGION_MAP["us"])

    async def authenticate(self, email: str | None = None, password: str | None = None) -> str:
        """Authenticate with LibreLinkUp and return auth token."""
        email = email or settings.libre_email
        password = password or settings.libre_password

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/llu/auth/login",
                headers=LLU_HEADERS,
                json={"email": email, "password": password},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            # Handle region redirect
            if data.get("data", {}).get("redirect"):
                region = data["data"]["region"]
                self._base_url = REGION_MAP.get(region, self._base_url)
                return await self.authenticate(email, password)

            self._token = data["data"]["authTicket"]["token"]
            user_id = data["data"]["user"]["id"]
            self._account_id_hash = hashlib.sha256(user_id.encode()).hexdigest()
            return self._token

    def _auth_headers(self, token: str | None = None) -> dict:
        t = token or self._token
        if not t:
            raise RuntimeError("Not authenticated — call authenticate() first")
        headers = {**LLU_HEADERS, "Authorization": f"Bearer {t}"}
        if self._account_id_hash:
            headers["account-id"] = self._account_id_hash
        return headers

    async def get_connections(self, token: str | None = None) -> list[dict]:
        """Get list of patients shared with this account."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/llu/connections",
                headers=self._auth_headers(token),
                timeout=15,
            )
            response.raise_for_status()
            return response.json().get("data", [])

    async def get_latest_reading(self, patient_id: str, token: str | None = None) -> dict | None:
        """Get latest glucose reading for a patient."""
        connections = await self.get_connections(token)
        for conn in connections:
            if conn.get("patientId") == patient_id:
                reading = conn.get("glucoseMeasurement", {})
                return {
                    "timestamp": reading.get("Timestamp"),
                    "glucose_mmol": reading.get("Value"),
                    "trend_arrow": reading.get("TrendArrow"),
                    "is_high": reading.get("isHigh", False),
                    "is_low": reading.get("isLow", False),
                }
        return None

    async def get_graph_data(self, patient_id: str, token: str | None = None) -> list[dict]:
        """Get glucose graph data (last ~12 hours) for a patient."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/llu/connections/{patient_id}/graph",
                headers=self._auth_headers(token),
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            readings = data.get("graphData", [])

            return [
                {
                    "timestamp": r.get("Timestamp"),
                    "glucose_mmol": r.get("Value"),
                    "is_high": r.get("isHigh", False),
                    "is_low": r.get("isLow", False),
                }
                for r in readings
            ]

    async def get_latest_for_user(self, user) -> dict | None:
        """Convenience: authenticate with user's stored credentials and fetch latest reading."""
        if not user.libre_auth_token or not user.libre_patient_id:
            logger.warning("User %s has no Libre credentials configured", user.id)
            return None
        try:
            return await self.get_latest_reading(
                patient_id=user.libre_patient_id,
                token=user.libre_auth_token,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.info("Libre token expired for user %s, re-authenticating", user.id)
                new_token = await self.authenticate()
                return await self.get_latest_reading(
                    patient_id=user.libre_patient_id,
                    token=new_token,
                )
            raise


libre_client = LibreLinkUpClient()
