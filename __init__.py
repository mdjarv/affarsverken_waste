"""The Affärsverken Waste Collection integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "affarsverken_waste"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Affärsverken Waste from a config entry."""
    # This method will be called when a config entry is loaded (e.g., after UI setup or HA restart).
    # It will forward the setup to the sensor platform.
    # Corrected method name from async_forward_entry_setup to async_forward_entry_setups
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, ["sensor"]) # Note: it expects a list of platforms
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This method will be called when a config entry is unloaded (e.g., when deleted from UI).
    # It will forward the unload to the sensor platform.
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")


