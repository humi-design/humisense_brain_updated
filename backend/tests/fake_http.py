"""Shared fake HTTP client used by connector tests (MOCK).

The connectors accept an injected ``http_client``, so tests exercise the real
connector code paths (headers, pagination, record shaping) without any network
access.  A passing test here means the connector *logic* works against a
simulated provider - it is **not** evidence of a live integration.
"""

from __future__ import annotations

import json
from typing import Any, Callable


class FakeResponse:
    def __init__(self, status_code: int, body: Any, headers: dict | None = None):
        self.status_code = status_code
        self._body = body
        self.headers = dict(headers or {})
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.content = self.text.encode()

    def json(self) -> Any:
        return json.loads(self.text) if isinstance(self._body, str) else self._body

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}


class FakeHttpClient:
    """Routes by ``(METHOD, path)``; a callable route receives kwargs."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.calls: list[dict] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        from urllib.parse import urlsplit

        path = urlsplit(url).path
        handler = self.routes.get((method.upper(), path)) or self.routes.get(("*", path))
        if handler is None:
            return FakeResponse(404, {"error": "not_found"})
        if callable(handler):
            return handler(url=url, **kwargs)
        return handler

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return await self.request("POST", url, **kwargs)


def static(status: int, body: Any, headers: dict | None = None) -> Callable[..., FakeResponse]:
    def _handler(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(status, body, headers)

    return _handler
