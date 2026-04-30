"""API client for Affärsverken Waste Collection."""
from __future__ import annotations

import logging
from datetime import date, datetime, UTC
from typing import Any
from urllib.parse import quote

import aiohttp
import jwt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    BUILDING_CACHE_LIFETIME,
    BUILDING_SEARCH_API_URL,
    LOGIN_API_URL,
    REQUEST_TIMEOUT,
    STORAGE_VERSION,
    TOKEN_EXPIRY_SAFETY,
    TOKEN_FALLBACK_LIFETIME,
    WASTE_COLLECTION_BASE_API_URL,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)


class AuthError(Exception):
    """Raised when the API rejects credentials."""


class ApiError(Exception):
    """Raised on transport/protocol errors."""


class AffarsverkenWasteApiClient:
    """Async client for the Affärsverken open API."""

    def __init__(self, hass: HomeAssistant, store: Store) -> None:
        self._hass = hass
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._store = store
        self._cache: dict[str, Any] | None = None

    async def _load_cache(self) -> dict[str, Any]:
        if self._cache is None:
            self._cache = await self._store.async_load() or {}
        return self._cache

    async def _save_cache(self) -> None:
        if self._cache is not None:
            await self._store.async_save(self._cache)

    async def _invalidate_token(self) -> None:
        cache = await self._load_cache()
        cache.pop("token", None)
        cache.pop("token_expiration_time", None)
        await self._save_cache()

    async def _get_auth_token(self, force_refresh: bool = False) -> str:
        cache = await self._load_cache()

        if not force_refresh:
            cached_token = cache.get("token")
            expiration_str = cache.get("token_expiration_time")
            if cached_token and expiration_str:
                try:
                    expires = datetime.fromisoformat(expiration_str)
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=UTC)
                    if datetime.now(UTC) < expires:
                        return cached_token
                except ValueError:
                    _LOGGER.debug("Bad cached expiration timestamp; refreshing")

        _LOGGER.debug("Requesting new authentication token")
        try:
            async with self._session.post(LOGIN_API_URL, timeout=_TIMEOUT) as resp:
                if resp.status in (401, 403):
                    raise AuthError(f"Login rejected: HTTP {resp.status}")
                resp.raise_for_status()
                token = (await resp.text()).strip()
        except aiohttp.ClientResponseError as err:
            raise ApiError(f"Login failed: {err.status} {err.message}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ApiError(f"Login transport error: {err}") from err

        if not token:
            raise ApiError("Login returned empty token")

        expires_at = self._extract_token_expiry(token)
        cache["token"] = token
        cache["token_expiration_time"] = expires_at.isoformat()
        await self._save_cache()
        return token

    @staticmethod
    def _extract_token_expiry(token: str) -> datetime:
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
        except jwt.DecodeError as err:
            _LOGGER.warning("Could not decode JWT: %s; using fallback lifetime", err)
            return datetime.now(UTC) + TOKEN_FALLBACK_LIFETIME

        exp = decoded.get("exp")
        if exp is None:
            _LOGGER.warning("JWT missing 'exp' claim; using fallback lifetime")
            return datetime.now(UTC) + TOKEN_FALLBACK_LIFETIME
        return datetime.fromtimestamp(exp, tz=UTC) - TOKEN_EXPIRY_SAFETY

    async def _authed_get(self, url: str) -> Any:
        for attempt in range(2):
            token = await self._get_auth_token(force_refresh=(attempt == 1))
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            try:
                async with self._session.get(
                    url, headers=headers, timeout=_TIMEOUT
                ) as resp:
                    if resp.status in (401, 403) and attempt == 0:
                        _LOGGER.info("Token rejected; retrying with fresh token")
                        await self._invalidate_token()
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as err:
                raise ApiError(f"GET {url} failed: {err.status} {err.message}") from err
            except (aiohttp.ClientError, TimeoutError) as err:
                raise ApiError(f"GET {url} transport error: {err}") from err
        raise AuthError("Token rejected even after refresh")

    async def _resolve_query_param(self, address: str) -> str:
        cache = await self._load_cache()
        buildings = cache.setdefault("buildings", {})
        cached = buildings.get(address)
        if cached:
            try:
                last_updated = datetime.fromisoformat(cached["last_updated"])
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=UTC)
                if datetime.now(UTC) - last_updated < BUILDING_CACHE_LIFETIME:
                    return cached["query_param"]
            except (KeyError, ValueError):
                pass

        _LOGGER.debug("Searching building id for %s", address)
        url = f"{BUILDING_SEARCH_API_URL}?address={quote(address, safe='')}"
        results = await self._authed_get(url)

        if not isinstance(results, list) or not results:
            raise ApiError(f"No building found for address: {address}")

        query_param = results[0].get("query")
        if not query_param:
            raise ApiError(f"Building entry missing 'query' field: {results[0]}")

        buildings[address] = {
            "query_param": query_param,
            "last_updated": datetime.now(UTC).isoformat(),
        }
        await self._save_cache()
        return query_param

    async def async_validate(self, address: str) -> None:
        """Hit the API to validate credentials and address."""
        await self._resolve_query_param(address)

    async def async_get_collection_dates(self, address: str) -> dict[str, date]:
        query_param = await self._resolve_query_param(address)
        url = f"{WASTE_COLLECTION_BASE_API_URL}{query_param}"
        data = await self._authed_get(url)
        return self._parse_collection_dates(data)

    @staticmethod
    def _parse_collection_dates(data: dict[str, Any]) -> dict[str, date]:
        dates: dict[str, date] = {}
        services = data.get("services")
        if not isinstance(services, list):
            _LOGGER.warning("'services' missing or not a list in API response")
            return dates

        for service in services:
            title = service.get("title")
            next_pickup = service.get("nextPickup")
            if not title or not next_pickup:
                continue
            try:
                dates[title] = datetime.strptime(next_pickup, "%Y-%m-%d").date()
            except ValueError:
                _LOGGER.warning("Unparseable date %s for %s", next_pickup, title)
        return dates
