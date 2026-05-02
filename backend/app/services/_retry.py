"""Shared HTTP retry utility for storage service calls."""
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx

_T = TypeVar("_T")

MAX_RETRIES = 3
RETRY_DELAY = 3.0


async def with_retry(
    coro_factory: Callable[[], Coroutine[Any, Any, _T]],
    label: str,
    logger: logging.Logger,
) -> _T:
    """Execute a coroutine, retrying up to MAX_RETRIES times on HTTP 5xx errors.

    Non-5xx HTTP errors (including 401) propagate immediately without retry.
    """
    last_exc: httpx.HTTPStatusError | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500 and attempt < MAX_RETRIES:
                logger.warning(
                    "%s: HTTP %s, retrying (%d/%d) in %.0fs...",
                    label, exc.response.status_code, attempt, MAX_RETRIES, RETRY_DELAY,
                )
                last_exc = exc
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise
    raise last_exc  # type: ignore[misc]
