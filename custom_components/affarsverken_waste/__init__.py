"""The Affärsverken Waste Collection integration."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .api import AffarsverkenWasteApiClient
from .const import DOMAIN, STORAGE_VERSION
from .coordinator import AffarsverkenWasteCoordinator
from .helpers import address_slug

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class RuntimeData:
    client: AffarsverkenWasteApiClient
    coordinator: AffarsverkenWasteCoordinator


type AffarsverkenWasteConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: AffarsverkenWasteConfigEntry) -> bool:
    """Set up Affärsverken Waste from a config entry."""
    address = entry.data[CONF_ADDRESS]
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    client = AffarsverkenWasteApiClient(hass, store)
    coordinator = AffarsverkenWasteCoordinator(hass, entry, client, address)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AffarsverkenWasteConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry data forward.

    v1 → v2: the address slug used in entity unique_ids and device identifiers
    is now derived from the normalized address (lowercased, whitespace
    collapsed) instead of the raw user input. Re-anchor existing registry
    rows so users keep their entity_ids and history, and drop any orphan
    rows the post-upgrade load created under the new id.
    """
    if entry.version >= 2:
        return True

    address = entry.data[CONF_ADDRESS]
    old_hash = hashlib.md5(address.encode(), usedforsecurity=False).hexdigest()[:8]
    new_hash = address_slug(address)

    if old_hash != new_hash:
        _migrate_entities(hass, entry, old_hash, new_hash)
        _migrate_device(hass, entry, old_hash, new_hash)
        _LOGGER.info(
            "Migrated affarsverken_waste entry %s: %s → %s",
            entry.entry_id,
            old_hash,
            new_hash,
        )

    hass.config_entries.async_update_entry(entry, version=2)
    return True


def _migrate_entities(
    hass: HomeAssistant, entry: ConfigEntry, old_hash: str, new_hash: str
) -> None:
    registry = er.async_get(hass)
    old_prefix = f"{DOMAIN}_{old_hash}_"

    for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if not entity.unique_id.startswith(old_prefix):
            continue
        suffix = entity.unique_id.removeprefix(old_prefix)
        new_unique_id = f"{DOMAIN}_{new_hash}_{suffix}"

        # If the post-upgrade load already created an entity at the new id,
        # drop it so the rename succeeds and the original (with history and
        # the user's preferred entity_id) wins.
        existing = registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id)
        if existing and existing != entity.entity_id:
            registry.async_remove(existing)

        registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)


def _migrate_device(hass: HomeAssistant, entry: ConfigEntry, old_hash: str, new_hash: str) -> None:
    registry = dr.async_get(hass)
    old_id = (DOMAIN, old_hash)
    new_id = (DOMAIN, new_hash)

    old_device = registry.async_get_device(identifiers={old_id})
    if old_device is None:
        return

    new_device = registry.async_get_device(identifiers={new_id})
    if new_device is not None and new_device.id != old_device.id:
        registry.async_remove_device(new_device.id)
    registry.async_update_device(old_device.id, new_identifiers={new_id})
