"""Polite HTTP: identifiable user agent, per-host spacing, retries."""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import httpx

USER_AGENT = os.environ.get(
    "TRACKER_USER_AGENT",
    "CA-Education-Agency-Tracker/0.1 (agenda monitoring; contact via repository owner)",
)
MAX_BYTES = 40 * 1024 * 1024


class FetchError(Exception):
    pass


class Fetcher:
    def __init__(self, min_interval: float = 1.0, retries: int = 3, timeout: float = 45.0):
        self.min_interval = min_interval
        self.retries = retries
        self._last_hit: dict[str, float] = {}
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        )

    def _wait_for_host(self, url: str) -> None:
        host = urlsplit(url).netloc
        wait = self._last_hit.get(host, 0) + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        """GET with retries; the body is capped at MAX_BYTES."""
        last: Exception | None = None
        for attempt in range(self.retries):
            self._wait_for_host(url)
            try:
                with self.client.stream("GET", url) as resp:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise FetchError(f"HTTP {resp.status_code} for {url}")
                    resp.raise_for_status()
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise FetchError(f"{url} is larger than {MAX_BYTES} bytes")
                    return httpx.Response(
                        resp.status_code, headers=resp.headers, content=bytes(body),
                        request=resp.request,
                    )
            except httpx.HTTPStatusError as e:
                raise FetchError(f"HTTP {e.response.status_code} for {url}") from e
            except (httpx.TransportError, FetchError) as e:
                last = e
                if isinstance(e, FetchError) and "larger than" in str(e):
                    raise
                time.sleep(2 ** attempt)
        raise FetchError(str(last))

    def close(self) -> None:
        self.client.close()
