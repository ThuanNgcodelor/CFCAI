import asyncio
import json
import logging
from typing import Any

# pyrefly: ignore[missing-import]
import httpx

from src.chatbot.core.settings import settings

logger = logging.getLogger(__name__)


class AmisCrmClient:
    """
    Python client for MISA AMIS CRM API v2.
    Direct drop-in replacement for the n8n FetchAmisData code node.
    """

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: float = 30.0,
        page_gap_seconds: float = 0.25,
        max_retries: int = 5,
    ):
        self.base_url = (base_url or settings.AMIS_BASE_URL).rstrip("/")
        self.client_id = client_id or settings.AMIS_CLIENT_ID
        self.client_secret = client_secret or settings.AMIS_CLIENT_SECRET
        self.timeout = timeout_seconds
        self.page_gap = page_gap_seconds
        self.max_retries = max_retries
        self._token: str | None = None

    async def _request_with_retry(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs
    ) -> httpx.Response:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await client.request(
                    method, url, timeout=self.timeout, **kwargs
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as err:
                last_error = err
                if attempt + 1 >= self.max_retries:
                    break
                backoff = min(15.0, (2**attempt)) + 0.1
                logger.warning(
                    f"[AMIS Client] Transient error on attempt {attempt + 1}/{self.max_retries}: {err}. Retrying in {backoff:.2f}s..."
                )
                await asyncio.sleep(backoff)
        raise RuntimeError(
            f"[AMIS Client] Request failed after {self.max_retries} attempts: {last_error}"
        )

    async def authenticate(self, client: httpx.AsyncClient | None = None) -> str:
        if not self.client_secret:
            raise ValueError("[AMIS Client] AMIS_CLIENT_SECRET is not configured.")

        should_close = False
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            url = f"{self.base_url}/Account"
            payload = {"client_id": self.client_id, "client_secret": self.client_secret}
            resp = await self._request_with_retry(
                client,
                "POST",
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            token = ""
            if isinstance(data.get("data"), str):
                token = data["data"]
            elif isinstance(data.get("data"), dict) and "access_token" in data["data"]:
                token = data["data"]["access_token"]

            if not token:
                raise RuntimeError(
                    f"[AMIS Client] Empty auth token in response: {str(data)[:200]}"
                )

            self._token = token
            return token
        finally:
            if should_close:
                await client.aclose()

    async def fetch_all_pages(
        self, resource: str, max_pages: int = 300, page_size: int = 100
    ) -> list[dict[str, Any]]:
        """
        Pagination loop matching n8n logic exactly:
        - 100 items per page
        - orderBy=modified_date&isDescending=true
        - Fingerprint deduplication check
        - 250ms gap between pages to respect AMIS rate limits
        """
        if not self._token:
            await self.authenticate()

        all_records: list[dict[str, Any]] = []
        seen_fingerprints = set()

        async with httpx.AsyncClient() as client:
            for page in range(max_pages):
                url = (
                    f"{self.base_url}/{resource}"
                    f"?page={page}&pageSize={page_size}&orderBy=modified_date&isDescending=true"
                )
                headers = {
                    "Authorization": f"Bearer {self._token}",
                    "Clientid": self.client_id,
                    "Accept": "application/json",
                }

                try:
                    resp = await self._request_with_retry(
                        client, "GET", url, headers=headers
                    )
                except Exception as e:
                    # Check for 401 Unauthorized to refresh token once
                    if "401" in str(e):
                        logger.info(
                            "[AMIS Client] Token expired (401), refreshing token..."
                        )
                        await self.authenticate(client)
                        headers["Authorization"] = f"Bearer {self._token}"
                        resp = await self._request_with_retry(
                            client, "GET", url, headers=headers
                        )
                    else:
                        raise

                payload = resp.json()
                records = []
                if isinstance(payload, list):
                    records = payload
                elif isinstance(payload.get("data"), list):
                    records = payload["data"]
                elif isinstance(payload.get("data"), dict) and isinstance(
                    payload["data"].get("items"), list
                ):
                    records = payload["data"]["items"]
                elif isinstance(payload.get("items"), list):
                    records = payload["items"]
                elif isinstance(payload.get("records"), list):
                    records = payload["records"]

                if not records:
                    break

                # Fingerprint check
                first_item_snippet = json.dumps(records[0])[:60] if records else ""
                fp = f"{resource}:p{page}:n{len(records)}:{first_item_snippet}"
                if fp in seen_fingerprints:
                    raise RuntimeError(
                        f"[AMIS Client] Repeated page detected for {resource}, aborting."
                    )
                seen_fingerprints.add(fp)

                all_records.extend(records)

                # Total count check
                total = payload.get("total") or payload.get("totalCount")
                if total is None and isinstance(payload.get("data"), dict):
                    total = payload["data"].get("total")
                if (
                    total is not None
                    and isinstance(total, int)
                    and len(all_records) >= total
                ):
                    break

                if len(records) < page_size:
                    break

                await asyncio.sleep(self.page_gap)

        return all_records
