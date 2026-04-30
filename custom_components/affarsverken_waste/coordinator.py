"""Coordinator for Affärsverken Waste Collection."""
from __future__ import annotations

import logging
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AffarsverkenWasteApiClient, ApiError, AuthError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AffarsverkenWasteCoordinator(DataUpdateCoordinator[dict[str, date]]):
    """Polls waste collection dates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AffarsverkenWasteApiClient,
        address: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self._client = client
        self._address = address

    async def _async_update_data(self) -> dict[str, date]:
        try:
            return await self._client.async_get_collection_dates(self._address)
        except AuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
