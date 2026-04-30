"""Pure helpers for the Affärsverken Waste Collection integration.

Kept HA-free so the logic is unit-testable without spinning up a HomeAssistant
instance.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any


def normalize_address(address: str) -> str:
    """Collapse whitespace and lowercase, used for stable identifiers."""
    return " ".join(address.split()).lower()


def address_slug(address: str, length: int = 8) -> str:
    """Short stable slug derived from the normalized address."""
    digest = hashlib.md5(normalize_address(address).encode()).hexdigest()
    return digest[:length]


def build_pickup_attributes(
    collection_date: date,
    today: date,
    waste_type: str,
    address: str,
) -> dict[str, Any]:
    """Derive sensor attributes for a single pickup date.

    Pure: takes `today` rather than reading the clock so tests can pin time.
    """
    days_until = (collection_date - today).days
    return {
        "days_until_pickup": days_until,
        "pickup_date": collection_date.isoformat(),
        "waste_type": waste_type,
        "address": address,
        "is_today": days_until == 0,
        "is_tomorrow": days_until == 1,
        "is_this_week": 0 <= days_until <= 7,
        "pickup_weekday": collection_date.strftime("%A"),
    }
