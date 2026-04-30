"""The Affärsverken Waste Collection integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import AffarsverkenWasteApiClient
from .const import DOMAIN, STORAGE_VERSION
from .coordinator import AffarsverkenWasteCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class RuntimeData:
    client: AffarsverkenWasteApiClient
    coordinator: AffarsverkenWasteCoordinator


type AffarsverkenWasteConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: AffarsverkenWasteConfigEntry
) -> bool:
    """Set up Affärsverken Waste from a config entry."""
    address = entry.data[CONF_ADDRESS]
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    client = AffarsverkenWasteApiClient(hass, store)
    coordinator = AffarsverkenWasteCoordinator(hass, entry, client, address)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AffarsverkenWasteConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
