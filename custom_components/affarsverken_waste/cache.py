"""Persistent cache for tokens and resolved building queries.

Wraps `homeassistant.helpers.storage.Store` with typed accessors so the API
client doesn't sling around a `dict[str, Any]` whose keys are stringly defined.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.helpers.storage import Store

from .const import (
    BUILDING_CACHE_LIFETIME,
    CACHE_KEY_BUILDINGS,
    CACHE_KEY_TOKEN,
    CACHE_KEY_TOKEN_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)


def _parse_iso_utc(value: str) -> datetime:
    """Parse an ISO timestamp, treating naive values as UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class WasteCache:
    """Lazy in-memory mirror of the persisted JSON cache."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._data: dict[str, Any] | None = None

    async def _load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = await self._store.async_load() or {}
        return self._data

    async def _save(self) -> None:
        if self._data is not None:
            await self._store.async_save(self._data)

    async def get_token(self) -> str | None:
        """Return a cached token if it's still within its expiry window."""
        data = await self._load()
        token = data.get(CACHE_KEY_TOKEN)
        expiry = data.get(CACHE_KEY_TOKEN_EXPIRY)
        if not token or not expiry:
            return None
        try:
            expires_at = _parse_iso_utc(expiry)
        except ValueError:
            _LOGGER.debug("Bad cached expiration timestamp; refreshing")
            return None
        if datetime.now(UTC) >= expires_at:
            return None
        return token

    async def set_token(self, token: str, expires_at: datetime) -> None:
        data = await self._load()
        data[CACHE_KEY_TOKEN] = token
        data[CACHE_KEY_TOKEN_EXPIRY] = expires_at.isoformat()
        await self._save()

    async def invalidate_token(self) -> None:
        data = await self._load()
        data.pop(CACHE_KEY_TOKEN, None)
        data.pop(CACHE_KEY_TOKEN_EXPIRY, None)
        await self._save()

    async def get_building_query(
        self,
        address: str,
        ttl: timedelta = BUILDING_CACHE_LIFETIME,
    ) -> str | None:
        """Return a cached `query` token for `address` if still fresh."""
        data = await self._load()
        entry = data.get(CACHE_KEY_BUILDINGS, {}).get(address)
        if not entry:
            return None
        try:
            last_updated = _parse_iso_utc(entry["last_updated"])
        except (KeyError, ValueError):
            return None
        if datetime.now(UTC) - last_updated >= ttl:
            return None
        return entry.get("query_param")

    async def set_building_query(self, address: str, query_param: str) -> None:
        data = await self._load()
        buildings = data.setdefault(CACHE_KEY_BUILDINGS, {})
        buildings[address] = {
            "query_param": query_param,
            "last_updated": datetime.now(UTC).isoformat(),
        }
        await self._save()
