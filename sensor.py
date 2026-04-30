"""Sensor platform for Affärsverken Waste Collection."""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import AffarsverkenWasteConfigEntry
from .const import DOMAIN
from .coordinator import AffarsverkenWasteCoordinator

_LOGGER = logging.getLogger(__name__)


def _normalize_address(address: str) -> str:
    return " ".join(address.split()).lower()


def _address_slug(address: str) -> str:
    return hashlib.md5(_normalize_address(address).encode()).hexdigest()[:8]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AffarsverkenWasteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for waste collection types found by the coordinator."""
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
        self._base_name = base_name
        self._address = address
        self._waste_type = waste_type

        self._attr_name = f"{base_name} {waste_type}"
        self._attr_unique_id = (
            f"{DOMAIN}_{_address_slug(address)}_{slugify(waste_type)}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, _address_slug(address))},
            "name": f"Waste Collection - {address}",
            "manufacturer": "Affärsverken",
            "model": "Waste Collection",
        }

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self._waste_type in self.coordinator.data
        )

    @property
    def native_value(self) -> date | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._waste_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        collection_date = self.coordinator.data.get(self._waste_type)
        if collection_date is None:
            return {}

        today = datetime.now().date()
        days_until = (collection_date - today).days
        return {
            "days_until_pickup": days_until,
            "pickup_date": collection_date.isoformat(),
            "waste_type": self._waste_type,
            "address": self._address,
            "is_today": days_until == 0,
            "is_tomorrow": days_until == 1,
            "is_this_week": 0 <= days_until <= 7,
            "pickup_weekday": collection_date.strftime("%A"),
        }
