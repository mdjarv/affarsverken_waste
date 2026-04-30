"""Pure parsers for Affärsverken API payloads.

No HA imports, no I/O — keeps this layer trivially testable.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import jwt

from .const import TOKEN_EXPIRY_SAFETY, TOKEN_FALLBACK_LIFETIME

_LOGGER = logging.getLogger(__name__)


def parse_collection_dates(payload: dict[str, Any]) -> dict[str, date]:
    """Pull `{title: nextPickup}` out of a waste-collection response.

    Skips entries with missing fields or unparseable dates rather than failing
    the whole refresh — the API occasionally omits one service while others
    are valid.
    """
    services = payload.get("services")
    if not isinstance(services, list):
        _LOGGER.warning("'services' missing or not a list in API response")
        return {}

    dates: dict[str, date] = {}
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


def extract_jwt_expiry(token: str) -> datetime:
    """Read `exp` from a JWT and subtract a safety margin.

    Falls back to a fixed lifetime if the token is malformed or `exp`-less,
    so an unparseable token still expires eventually rather than being
    cached forever.
    """
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
