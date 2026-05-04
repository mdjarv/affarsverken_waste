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

    v1 → v2: entity unique_id slug switched from md5(raw_address) to
    md5(normalized_address); rename old rows and drop any orphan new-id
    rows the post-upgrade load created.

    v2 → v3: legacy device identifier was (DOMAIN, raw_address); v0.2.0
    introduced (DOMAIN, address_slug) as a *new* device alongside the
    legacy one, leaving two devices per entry. Collapse to one and
    preserve user-set area / name from whichever side has them.

    Both steps are idempotent and run from any prior version because
    v0.2.1's migration mistakenly bumped entries to version=2 without
    cleaning up the legacy device.
    """
    if entry.version >= 3:
        return True

    address = entry.data[CONF_ADDRESS]
    new_hash = address_slug(address)
    old_hash = hashlib.md5(address.encode(), usedforsecurity=False).hexdigest()[:8]

    if old_hash != new_hash:
        _migrate_entities(hass, entry, old_hash, new_hash)
    _migrate_devices(hass, entry, new_hash)

    hass.config_entries.async_update_entry(entry, version=3)
    _LOGGER.info("Migrated affarsverken_waste entry %s to v3", entry.entry_id)
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


def _migrate_devices(hass: HomeAssistant, entry: ConfigEntry, new_hash: str) -> None:
    registry = dr.async_get(hass)
    new_identifier = (DOMAIN, new_hash)

    devices = list(dr.async_entries_for_config_entry(registry, entry.entry_id))
    canonical: dr.DeviceEntry | None = None
    legacy: list[dr.DeviceEntry] = []
    for device in devices:
        if new_identifier in device.identifiers:
            canonical = device
        else:
            legacy.append(device)

    if not legacy:
        return

    if canonical is None:
        # Single legacy device (no canonical existed yet) — re-anchor it.
        keeper = legacy.pop(0)
        registry.async_update_device(keeper.id, new_identifiers={new_identifier})
        canonical = keeper

    # Lift user-set area and name from legacy onto canonical when canonical
    # is missing them — first legacy with a value wins. Anything the user
    # explicitly set on canonical is preserved.
    if canonical.area_id is None:
        for device in legacy:
            if device.area_id is not None:
                registry.async_update_device(canonical.id, area_id=device.area_id)
                break
    if canonical.name_by_user is None:
        for device in legacy:
            if device.name_by_user is not None:
                registry.async_update_device(canonical.id, name_by_user=device.name_by_user)
                break

    for device in legacy:
        registry.async_remove_device(device.id)
