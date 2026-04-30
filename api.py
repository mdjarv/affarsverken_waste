"""HTTP client for the Affärsverken open API.

This layer is pure transport: cache logic lives in `cache.py`, payload parsing
in `parsers.py`. Anything domain-stable belongs in those modules, not here.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .cache import WasteCache
from .const import (
    BUILDING_SEARCH_API_URL,
    LOGIN_API_URL,
    REQUEST_TIMEOUT,
    WASTE_COLLECTION_BASE_API_URL,
)
from .parsers import extract_jwt_expiry, parse_collection_dates

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
_AUTH_FAIL_STATUSES = (401, 403)


class AuthError(Exception):
    """Raised when the API rejects credentials."""


class ApiError(Exception):
    """Raised on transport/protocol errors."""


class AffarsverkenWasteApiClient:
    """Async client for the Affärsverken open API."""

    def __init__(self, hass: HomeAssistant, store: Store) -> None:
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._cache = WasteCache(store)

    async def async_validate(self, address: str) -> None:
        """Hit the API to validate credentials and address."""
        await self._resolve_query_param(address)

    async def async_get_collection_dates(self, address: str) -> dict[str, date]:
        """Return `{waste_type: next_pickup_date}` for `address`."""
        query_param = await self._resolve_query_param(address)
        url = f"{WASTE_COLLECTION_BASE_API_URL}{query_param}"
        payload = await self._authed_get(url)
        return parse_collection_dates(payload)

    # --- auth ----------------------------------------------------------------

    async def _get_auth_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            cached = await self._cache.get_token()
            if cached:
                return cached
        return await self._fetch_and_store_token()

    async def _fetch_and_store_token(self) -> str:
        _LOGGER.debug("Requesting new authentication token")
        try:
            async with self._session.post(LOGIN_API_URL, timeout=_TIMEOUT) as resp:
                if resp.status in _AUTH_FAIL_STATUSES:
                    raise AuthError(f"Login rejected: HTTP {resp.status}")
                resp.raise_for_status()
                token = (await resp.text()).strip()
        except aiohttp.ClientResponseError as err:
            raise ApiError(f"Login failed: {err.status} {err.message}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ApiError(f"Login transport error: {err}") from err

        if not token:
            raise ApiError("Login returned empty token")

        await self._cache.set_token(token, expires_at=extract_jwt_expiry(token))
        return token

    # --- transport -----------------------------------------------------------

    async def _authed_get(self, url: str) -> Any:
        """GET `url` with auth, retrying once on 401/403 with a fresh token."""
        try:
            return await self._get_with_token(url, force_refresh=False)
        except AuthError:
            _LOGGER.info("Token rejected; retrying with fresh token")
            await self._cache.invalidate_token()
            return await self._get_with_token(url, force_refresh=True)

    async def _get_with_token(self, url: str, *, force_refresh: bool) -> Any:
        token = await self._get_auth_token(force_refresh=force_refresh)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        try:
            async with self._session.get(
                url, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status in _AUTH_FAIL_STATUSES:
                    raise AuthError(f"Token rejected: HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientResponseError as err:
            raise ApiError(f"GET {url} failed: {err.status} {err.message}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ApiError(f"GET {url} transport error: {err}") from err

    # --- building lookup -----------------------------------------------------

    async def _resolve_query_param(self, address: str) -> str:
        cached = await self._cache.get_building_query(address)
        if cached:
            return cached
        return await self._fetch_and_store_building_query(address)

    async def _fetch_and_store_building_query(self, address: str) -> str:
        _LOGGER.debug("Searching building id for %s", address)
        url = f"{BUILDING_SEARCH_API_URL}?address={quote(address, safe='')}"
        results = await self._authed_get(url)

        if not isinstance(results, list) or not results:
            raise ApiError(f"No building found for address: {address}")

        query_param = results[0].get("query")
        if not query_param:
            raise ApiError(f"Building entry missing 'query' field: {results[0]}")

        await self._cache.set_building_query(address, query_param)
        return query_param
