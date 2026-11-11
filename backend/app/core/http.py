"""Egress-guarded async HTTP client.

All connector HTTP traffic goes through :class:`GuardedHttpClient`.  It
enforces the SSRF/egress policy on every request, applies timeouts, honours
``Retry-After`` on 429/503, and retries transient failures with exponential
backoff plus jitter.  Retries are bounded so a dead provider cannot spin.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from app.core.config import settings
from app.core.egress import guard_url
from app.core.errors import (
    ConnectorRateLimited,
    ConnectorTransientError,
    EgressBlockedError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GuardedHttpClient:
    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        allow_private: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        verify: bool = True,
    ) -> None:
        self.timeout = timeout or settings.connector_request_timeout_seconds
        self.max_retries = settings.connector_max_retries if max_retries is None else max_retries
        self.allow_private = allow_private
        self._transport = transport
        self._verify = verify

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=False,  # redirects are validated explicitly
            verify=self._verify,
            transport=self._transport,
        )

    def _backoff(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(max(retry_after, 0.0), settings.sync_backoff_max_seconds)
        base = settings.sync_backoff_base_seconds * (2 ** attempt)
        jitter = random.uniform(0, base * 0.25)
        return min(base + jitter, settings.sync_backoff_max_seconds)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: Any | None = None,
        content: bytes | None = None,
        allow_redirects: bool = False,
    ) -> httpx.Response:
        target = guard_url(url, allow_private=self.allow_private)
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.max_retries:
            try:
                async with self._client() as client:
                    response = await client.request(
                        method,
                        target.url,
                        headers=headers,
                        params=params,
                        json=json_body,
                        data=data,
                        content=content,
                    )
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                    httpx.PoolTimeout, httpx.RemoteProtocolError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ConnectorTransientError(
                        f"Connection to {target.host} failed after {attempt + 1} attempts."
                    ) from exc
                await asyncio.sleep(self._backoff(attempt))
                attempt += 1
                continue

            if response.status_code in _RETRYABLE_STATUS:
                retry_after = _parse_retry_after(response)
                if response.status_code == 429:
                    if attempt >= self.max_retries:
                        raise ConnectorRateLimited(
                            f"Rate limited by {target.host} after {attempt + 1} attempts.",
                            retry_after=retry_after,
                        )
                elif attempt >= self.max_retries:
                    raise ConnectorTransientError(
                        f"{target.host} returned {response.status_code} after "
                        f"{attempt + 1} attempts."
                    )
                await asyncio.sleep(self._backoff(attempt, retry_after))
                attempt += 1
                continue

            if allow_redirects and response.is_redirect:
                location = response.headers.get("location")
                if location:
                    return await self.request(
                        "GET", location, headers=headers, allow_redirects=allow_redirects
                    )
                raise EgressBlockedError("Redirect without a Location header.")

            return response

        raise ConnectorTransientError(f"Request to {target.host} failed.") from last_exc

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
