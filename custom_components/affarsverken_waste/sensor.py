"""Sensor platform for Affärsverken Waste Collection."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from . import AffarsverkenWasteConfigEntry
from .const import DOMAIN
from .coordinator import AffarsverkenWasteCoordinator
from .helpers import address_slug, build_pickup_attributes

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AffarsverkenWasteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for waste collection types as the coordinator discovers them."""
    coordinator = entry.runtime_data.coordinator
    address = entry.data[CONF_ADDRESS]
    base_name = entry.data.get(CONF_NAME, address)

    known: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        if not coordinator.data:
            return
        new_types = set(coordinator.data) - known
        if not new_types:
            return
        known.update(new_types)
        async_add_entities(
            AffarsverkenWasteSensor(coordinator, base_name, address, waste_type)
            for waste_type in new_types
        )

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class AffarsverkenWasteSensor(
    CoordinatorEntity[AffarsverkenWasteCoordinator], SensorEntity
):
    """Sensor for one waste collection type at one address."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:trash-can"
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: AffarsverkenWasteCoordinator,
        base_name: str,
        address: str,
        waste_type: str,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._waste_type = waste_type

        slug = address_slug(address)
        self._attr_name = f"{base_name} {waste_type}"
        self._attr_unique_id = f"{DOMAIN}_{slug}_{slugify(waste_type)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, slug)},
            name=f"Waste Collection - {address}",
            manufacturer="Affärsverken",
            model="Waste Collection",
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self._waste_type in self.coordinator.data
        )

    @property
    def native_value(self) -> date | None:
        data = self.coordinator.data
        return data.get(self._waste_type) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        collection_date = self.native_value
        if collection_date is None:
            return {}
        return build_pickup_attributes(
            collection_date=collection_date,
            today=dt_util.now().date(),
            waste_type=self._waste_type,
            address=self._address,
        )
